# ADR-0001 — Cascata com short-circuit, orçamento de latência e escada de degradação

- **Status:** aceito (revisado em 2026-08-25)
- **Substitui:** proposta de 2026-08-14 (avaliação paralela de todas as camadas e rebaixamento
  da Regra 83 a sinal), baseada em AS-IS que o briefing versão final não adota
- **Contexto AS-IS:** [`docs/arquitetura/00-contexto-as-is.md`](../arquitetura/00-contexto-as-is.md)
- **Orçamento:** [`docs/arquitetura/orcamento-de-latencia.md`](../arquitetura/orcamento-de-latencia.md)
- **Lacunas endereçadas:** L4 (short-circuit oculta o XGBoost), L9 (log síncrono)

## Contexto

### AS-IS

O microserviço FastAPI decide em cascata:

```text
validação → bundle HBOS → features → HBOS + regras → hard-rule de viagem impossível
→ se HBOS = deny: decisão final deny (XGBoost NÃO executa)
→ se HBOS = approve ou challenge: XGBoost global → consolidação dual
```

A meta é p95 < 100 ms. O short-circuit do `deny` do HBOS existe para não gastar os 15 ms
orçados ao XGBoost nos casos já encerrados.

### Lacuna/Risco

- Camada não executada não deixa score. Retreino e análise de incidente herdam o viés do
  short-circuit.
- Cache miss de bundle sem timeout de 20 ms estoura o hard deadline.
- Dependência externa no fast path (bureau, AutoML, device) é incompatível com 100 ms.
- A proposta anterior deste ADR tratava a Regra 83 como gate do score e o approve do HBOS
  como terminal. Essa leitura está registrada como divergência aberta
  ([D-3](../arquitetura/divergencias-documentais.md), [D-4](../arquitetura/divergencias-documentais.md)),
  não como produção deste microserviço.

## Decisão

**1. A cascata permanece.** Short-circuit de `HBOS = deny` é política de latência vigente, não
bug a remover nesta fase. Mudança de topologia (avaliação paralela, HBOS nunca terminal) só
pode ser reaberta depois da instrumentação e do diagnóstico de modelagem
([MAPA Etapa 1–4](../mlops/acompanhamento-modelagem.md)).

**2. Hard rules críticas prevalecem sobre scores.** Viagem impossível e demais vetos
determinísticos encerram com reason code próprio, independentemente do HBOS e do XGBoost.

**3. Escada de degradação obrigatória** — números do briefing:

| Falha | Comportamento | Reason code | Limiar |
|---|---|---|---|
| Cache miss do bundle HBOS | PostgreSQL com timeout **20 ms**; senão XGBoost + regras + hard rules; warm-up assíncrono | `hbos_unavailable` | nunca esperar I/O além do timeout |
| Falha do XGBoost | mantém HBOS + regras (fail-safe já existente) | `xgb_unavailable` | — |
| Dependência externa | **proibida no fast path** | — | validadores só na trilha de challenge |

**4. Observabilidade do short-circuit é pré-requisito, não melhoria.** 100% das transações
registram `layers_executed`, `layers_skipped`, `short_circuit_layer`, scores (null se não
executou), `fallback_reason` e `model_versions`. Amostra shadow **1% a 5%** avalia
assincronamente todas as camadas, inclusive o XGBoost nos `deny` do HBOS.

**5. Log e evento são fire-and-forget (0 ms no orçamento síncrono).**

### Fluxo TO-BE (hot path)

```text
POST /api/v1/score-transaction
→ validação Pydantic (≤ 5 ms)
→ carga bundle HBOS: cache hit (≤ 8 ms) | miss → PG ≤ 20 ms | timeout → fallback
→ features (≤ 25 ms)
→ HBOS + regras + hard-rule viagem impossível (≤ 12 ms)
→ se hard rule crítica: deny + reason code (short-circuit de negócio)
→ se HBOS = deny: deny final; XGBoost skipped; short_circuit_layer = hbos
→ senão: XGBoost (≤ 15 ms) → consolidação dual (≤ 5 ms)
→ resposta { decision_final } + enqueue de log/evento (0 ms síncronos)
```

## Alternativa considerada e adiada

Avaliação paralela de HBOS, GBDT, regras e grafo, com short-circuit só em hard rule, foi
proposta em 2026-08-14. **Não é a decisão vigente.** Motivos:

- o briefing versão final preserva a cascata e o orçamento que a justifica;
- o MAPA exige diagnóstico (rótulos, viés, baseline) antes de fechar linha de modelagem ou de
  topologia;
- a relação NEG83 × score (D-3) está aberta — rebaixar "Regra 83 a sinal" pressupõe que ela é
  gate deste serviço.

A alternativa volta à pauta se a amostra shadow (1%–5%) mostrar, em janela temporal com
rótulos maduros, que o XGBoost reverteria ≥ um limiar de negócio dos `deny` do HBOS com
fraude confirmada abaixo de um limiar de FPR definido pela operação. Sem esses números, não
há decisão de topologia a tomar.

## Consequências

- Latência continua sendo o vinculo da arquitetura: features (25 ms) são o maior consumidor;
  inferência do XGBoost (15 ms) só é gasta quando o HBOS não encerrou.
- Fail-safe da cascata permanece: XGBoost não é ponto único de falha.
- Custo: telemetria e shadow. Sem eles, o short-circuit continua cego.
- HBOS `deny` terminal persiste como risco de negócio (anomalia ≠ fraude). Mitigação imediata
  é medir, não desligar o short-circuit.

## Critérios de aceite

- p95 do fast path < 100 ms, com histograma por etapa nos budgets da tabela do briefing.
- 100% das transações com `short_circuit_layer` ∈ {`hbos`, `hard_rule`, `null`}.
- 100% dos scores de camada não executada iguais a `null`.
- Cache miss de bundle: timeout síncrono ≤ 20 ms em 100% dos casos; reason code
  `hbos_unavailable` quando degradado.
- Amostra shadow configurável entre 1% e 5%, assíncrona, sem efeito mensurável no p95
  (< 1 ms de acréscimo).
- Zero spans de autorização com chamada a bureau, AutoML, LLM ou device intelligence.
- Relatório mensal de divergência HBOS × XGBoost na amostra shadow, quebrado por decisão.
