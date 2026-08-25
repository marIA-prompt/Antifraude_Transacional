# Contexto AS-IS do motor de score antifraude

Documento de referência do **estado atual do microserviço FastAPI**. Tudo aqui descreve o que
existe hoje ou o que é sabidamente ambíguo. Propostas de evolução ficam nos ADRs em
[`docs/adr/`](../adr/). Briefing normativo:
[`docs/contexto-operacional.md`](../contexto-operacional.md).

> Convenção usada em todos os documentos deste repositório:
> **AS-IS** (o que existe) · **Lacuna/Risco** (limitação ou risco operacional) ·
> **TO-BE** (evolução proposta) · **Critério de aceite** (como comprovar objetivamente).

> AutoML, agentes de IA e Agent Framework Workflows **não existem no código atual**. São
> evolução, não estado presente.

## AS-IS: fluxo de decisão vigente

O sistema é um microserviço síncrono em FastAPI que, no momento da autorização do pagamento,
recebe os dados da transação e devolve uma decisão de risco. A meta de performance é **p95
abaixo de 100 ms no fast path**. Orçamento por etapa em
[`orcamento-de-latencia.md`](orcamento-de-latencia.md).

```text
POST /api/v1/score-transaction
→ validação (CPF 11 dígitos, CNPJ 14 dígitos, valores positivos, tipos)
→ carga do bundle HBOS do CPF (PostgreSQL + cache em memória)
→ cálculo de features (perfis salvos no bundle)
→ HBOS + regras de negócio (média ponderada)
→ hard-rule de viagem impossível
→ [se HBOS = deny → decisão final deny; XGBoost NÃO executa]
→ [se HBOS = approve ou challenge → XGBoost global]
→ consolidação dual (média ponderada)
→ persistência de log completo (assíncrona no TO-BE; ver orçamento)
→ resposta: { "decision_final": "approve | challenge | deny" }
```

| Decisão | Significado de negócio |
|---|---|
| `approve` | Transação dentro do padrão — seguir fluxo normal |
| `challenge` | Caso questionável — merece atenção adicional |
| `deny` | Alto risco — negar/bloquear |

Três propriedades desse desenho condicionam o restante da arquitetura:

1. **O `deny` do HBOS é terminal.** O modelo supervisionado não audita esses casos no caminho
   síncrono. Isso protege os 15 ms orçados para o XGBoost, mas exige instrumentação e shadow
   ([telemetria](../observabilidade/telemetria-de-decisao.md)).
2. **HBOS não é prova de fraude.** Score alto significa comportamento atípico. A razão de
   existir do HBOS é entregar valor imediato mesmo com rótulo atrasado.
3. **A resposta HTTP expõe só `decision_final`.** Score, sinais, features e pesos ficam no log.
   O orquestrador de `challenge` não deve depender dessa resposta.

**Fundações já prontas (AS-IS):** decisão em camadas, log auditável, treino noturno + fila,
cascata dual, cache de modelos, testes automatizados, separação online/offline.

## AS-IS: componentes de decisão

### HBOS individual por CPF

| Aspecto | AS-IS |
|---|---|
| Tipo | Não supervisionado, detecção de anomalia |
| Treino | Offline, um modelo por CPF |
| Artefato | Bundle serializado: modelo + scaler + perfis (média do CPF, cartões, estabelecimentos, centróide geográfico) |
| Serving | Cache em memória sobre PostgreSQL |
| Janela | Até ~730 dias |
| Semântica | Score alto = comportamento atípico, **não prova de fraude** |

### XGBoost global

| Aspecto | AS-IS |
|---|---|
| Tipo | Supervisionado, treinado com fraude confirmada |
| Papel | Segunda linha estatística em cascata; não é ponto único de falha |
| Fail-safe | Se o XGBoost falha, a decisão do HBOS + regras permanece (`xgb_unavailable`) |
| Cobertura | CPF novo e padrões de fraude em escala |
| Dependência | Qualidade e maturação dos rótulos; validação temporal obrigatória |

### Regras de negócio e hard rules

- Regras de valor, tempo, estabelecimento e geo.
- **Hard-rule de viagem impossível** — cenário clássico capturado com alta precisão.
- Hard rules críticas prevalecem sobre scores probabilísticos.
- Toda regra gera evidência e reason code auditável.

## AS-IS: contrato HTTP

Implementação vigente:

```json
{ "decision_final": "approve | challenge | deny" }
```

A especificação original do microserviço previa `score`, `decision`, `signals`, `features` e
`feature_weights`. Tratamento em [`api-versionada.md`](../contratos/api-versionada.md) e
registro em [`divergencias-documentais.md`](divergencias-documentais.md).

## O que comprovadamente **não** existe hoje

Registro explícito para evitar que planejamento seja lido como estado atual:

- AutoML / Azure AutoML no hot path **e** como esteira formalizada de promoção.
- Agent Framework Workflows e agentes de IA.
- Fluxo operacional completo de `challenge` (evento, fila, validadores, step-up, escalate,
  notificação idempotente).
- Invalidação automática de cache após publicação de modelo.
- Política de cold start configurável por faixa de valor, com reason code `cold_start`.
- API v2 com explicabilidade autenticada.
- Schema registry com lista canônica de features.
- Amostragem shadow das camadas suprimidas pelo short-circuit.

## Lacunas e riscos consolidados

| # | Lacuna / Risco | Impacto | Tratamento proposto |
|---|---|---|---|
| L1 | `challenge` sem fluxo operacional | Caso questionável pode não acionar fila, step-up, análise humana ou notificação | [Trilha de challenge](../workflows/trilha-de-challenge.md) |
| L2 | Cache de modelos exige restart ou limpeza manual após retreino | Instâncias servindo versões distintas sem detecção | [ADR-0004](../adr/0004-publicacao-de-modelos-e-cache.md) |
| L3 | Cold start de CPF novo indefinido neste fluxo | Peso do HBOS sobre histórico insuficiente; exposição em conta nova | [ADR-0003](../adr/0003-politica-de-cold-start.md) |
| L4 | Short-circuit do `deny` do HBOS oculta o XGBoost | Impossível medir o que o supervisionado teria feito; viés de seleção no retreino | [Telemetria](../observabilidade/telemetria-de-decisao.md) |
| L5 | API v1 não expõe explicabilidade | Consumidores autorizados sem score/sinais; orquestração tende a acoplar-se ao HTTP | [Contrato versionado](../contratos/api-versionada.md) |
| L6 | Lista de features não conciliada (10 × 13) | Contrato de modelo e documentação divergem; risco de leakage e de feature errada em produção | [Divergências](divergencias-documentais.md) · [Features](../contratos/features.md) |
| L7 | Rótulos sujeitos a maturação tardia | `sem_desfecho` tratado como legítima corrompe o treino | [MLOps](../mlops/dados-rotulos-e-promocao.md) |
| L8 | Relação entre NEG83 / Motor H e este microserviço não confirmada | Risco de tratar um autenticador operacional como gate deste score, ou o inverso | [Divergências D-3](divergencias-documentais.md) · [Motor H](../recuperacao/motor-h-neg83.md) |
| L9 | Persistência de log no caminho síncrono | Consome orçamento de latência que o briefing reserva a 0 ms (fire-and-forget) | [Orçamento](orcamento-de-latencia.md) |

## Perguntas abertas

Itens que dependem de confirmação com evidência de produção. Enquanto não resolvidos, **não
afirmar uma leitura como definitiva**:

1. Qual a lista canônica de features efetivamente calculadas no código (item L6 / D-2)?
2. Qual o threshold efetivo que transforma score HBOS em `deny` terminal, e onde está
   configurado?
3. Qual a taxa de `deny` encerrado no HBOS sem XGBoost, e qual a fraude confirmada nessa
   fatia (amostra shadow de 1% a 5%)?
4. O payload AS-IS trafega CPF/CNPJ em claro na validação Pydantic? Qual o ponto de
   tokenização?
5. Qual a relação operacional entre a regra NEG83, o step-up via WhatsApp e este
   microserviço FastAPI (item L8 / D-3)?
6. Existe model registry hoje, ainda que informal (bucket versionado, convenção de nomes)?
7. Qual a janela real de maturação de rótulo (dias entre transação e confirmação de fraude)?
8. Quantidade, maturação e representatividade dos rótulos históricos — inclusive a ausência
   relatada de fraude confirmada nos últimos seis meses (ver
   [acompanhamento de modelagem](../mlops/acompanhamento-modelagem.md)).
