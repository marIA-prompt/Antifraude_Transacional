# ADR-0001 — Topologia de decisão: avaliação paralela e camada de política

- **Status:** proposto
- **Contexto AS-IS:** [`docs/arquitetura/00-contexto-as-is.md`](../arquitetura/00-contexto-as-is.md)
- **Lacunas endereçadas:** L1 (cobertura de ML condicionada ao gate), L2 (approve terminal do
  HBOS), L7 (short-circuit oculta camadas posteriores)

## Contexto

O fluxo vigente encadeia as camadas em cascata com short-circuit: a Regra 83 decide quem é
elegível a ser analisado por modelo, e o approve do HBOS encerra a decisão antes do XGBoost.
A justificativa histórica é a meta de p95 abaixo de 100 ms.

O ponto central deste ADR é que **essa justificativa não se sustenta no orçamento de latência
real**. O custo dominante do fast path é a busca de features, e ela é compartilhada por todas
as camadas. A inferência propriamente dita custa poucos milissegundos.

### Orçamento de latência estimado (fast path)

| Etapa | Custo típico | Observação |
|---|---|---|
| Validação de payload e autenticação | 2–5 ms | |
| Busca única de features online | 10–20 ms | Etapa dominante; I/O de rede |
| Hard rules, blocklist, velocity | 3–5 ms | Em memória / cache local |
| HBOS do CPF | 1–3 ms | Bundle já em cache de memória |
| GBDT global | 1–5 ms | Algumas centenas de árvores |
| Calibração e política de decisão | < 1 ms | |
| Publicação do evento e logs | 0 ms no caminho síncrono | Assíncrono, fire-and-forget |

Total estimado de 25–35 ms, com folga confortável dentro dos 100 ms de meta. Pular o modelo
global quando o HBOS aprova economiza poucos milissegundos e, em troca, custa o sinal
supervisionado, a cobertura de ML na maior parte do tráfego e a base de dados não enviesada
necessária para retreinar.

## Decisão

**1. Uma única busca de features por transação.** Todas as camadas consomem o mesmo conjunto
materializado, obtido em uma chamada ao armazenamento online. A busca de features é o
orçamento que precisa ser protegido, não a inferência.

**2. Avaliação paralela das camadas de sinal.** HBOS, GBDT global, regras de negócio e
features de grafo pré-computadas são avaliados em paralelo sobre as mesmas features. Nenhuma
delas emite decisão terminal.

**3. Short-circuit restrito a hard rules críticas.** Encerrar antecipadamente passa a ser uma
decisão de negócio (blocklist confirmada, device banido, viagem impossível), nunca uma
otimização de latência. Todo short-circuit registra a regra que o causou e seu reason code.

**4. A decisão nasce em uma camada de política determinística.** Thresholds por valor, canal,
produto, tipo de transação e coorte, mais overrides de regra, aplicados sobre a probabilidade
calibrada e os sinais. A política é configuração versionada, não código.

**5. A Regra 83 deixa de ser gate e passa a ser sinal.** Continua produzindo evidência e
reason code próprios, e continua podendo influenciar a decisão pela camada de política — mas
não determina mais quem é elegível a receber escore.

### Fluxo TO-BE

```text
Transação
→ validação de payload + autenticação
→ busca única de features (perfil do CPF, velocity, device, merchant, geo, grafo)
→ hard rules críticas → deny imediato (único short-circuit permitido)
→ em paralelo:
     ├── HBOS individual por CPF        → score + contribuições por feature
     ├── GBDT global (ou cold start)    → score
     ├── regras de negócio (inclui R83) → sinais + reason codes
     └── features de grafo              → sinais
→ calibração de probabilidade (artefato versionado)
→ camada de política: thresholds por valor/canal/produto/coorte + overrides de regra
→ approve / challenge / deny + reason codes
→ evento interno assíncrono com score, sinais, features, pesos e versões
```

## Consequências

### Positivas

- Cobertura de ML em 100% do tráfego autorizado, eliminando a fonte estrutural de viés de
  seleção no retreinamento.
- Auditabilidade: sempre existe escore e reason code, mesmo em approve.
- A camada de política concentra a decisão em um ponto único, testável e configurável sem
  redeploy dos modelos.
- Habilita a observabilidade completa exigida em
  [telemetria de decisão](../observabilidade/telemetria-de-decisao.md), porque nenhuma camada
  deixa de ser executada por padrão.

### Negativas e riscos

- **Custo computacional maior por transação**, já que todas as camadas rodam sempre. Mitigação:
  o custo incremental é de CPU, não de I/O; deve ser medido em carga antes do rollout.
- **Mudança de perfil de decisão.** Transações hoje aprovadas pelo gate passarão a receber
  escore e podem virar `challenge` ou `deny`. Sem controle, isso aumenta atrito e volume de
  fila de forma abrupta. Mitigação obrigatória: rollout em shadow antes de qualquer efeito
  sobre a decisão (ver abaixo).
- **Dependência de calibração.** Com a política centralizada em probabilidade calibrada, uma
  calibração degradada desloca simultaneamente as taxas de challenge e deny. Ver
  [ADR-0002](0002-papeis-dos-modelos.md).
- **Regressão de latência** se a busca de features não for consolidada em uma chamada. Sem o
  item 1, a paralelização multiplica I/O em vez de compartilhá-lo.

## Plano de rollout

1. **Shadow puro.** As camadas passam a ser avaliadas para todo o tráfego, mas a decisão
   continua saindo do fluxo atual. Objetivo: medir divergência e estimar o impacto de atrito.
2. **Medição de impacto.** Relatório de quantas transações hoje aprovadas pelo gate receberiam
   `challenge` ou `deny`, com fraude confirmada por banda de escore na fatia fora do gate.
3. **Calibração dos thresholds** da camada de política contra a capacidade operacional da fila
   de challenge e o apetite de risco definido pelo negócio.
4. **Rollout canário** por percentual de tráfego, com métricas por coorte e rollback imediato
   para a topologia anterior por configuração.
5. **Promoção** da nova topologia a padrão, mantendo o caminho antigo desabilitável por flag
   por um ciclo completo de maturação de rótulo.

## Critérios de aceite

- Nenhuma transação é decidida sem escore de modelo, exceto por hard rule crítica
  explicitamente documentada e com reason code registrado.
- p95 do fast path permanece abaixo de 100 ms com todas as camadas ativas, medido em carga
  representativa de pico.
- 100% das transações registram `camadas_executadas`, `camadas_nao_executadas` e
  `camada_que_encerrou`.
- A busca de features acontece uma única vez por transação, comprovado por tracing.
- Thresholds da camada de política são alteráveis sem redeploy, com versionamento e trilha de
  auditoria de quem alterou o quê.
- Rollback para a topologia anterior é acionável por configuração, sem deploy.
- Relatório de fraude confirmada por banda de escore disponível para as três coortes: tráfego
  fora do gate, approve terminal do HBOS e decidido pelo modelo global.
