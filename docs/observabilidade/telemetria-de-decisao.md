# Telemetria de decisão, short-circuit e shadow

## AS-IS

A cascata encerra antecipadamente quando `HBOS = deny` (XGBoost não executa) e quando uma
hard rule crítica veta. O briefing exige instrumentação; o registro estruturado por
transação com os campos abaixo **não** está descrito como contrato vigente — o log completo
existe como fundação, mas sem garantia dos nomes canônicos.

## Lacuna/Risco

- Camadas posteriores invisíveis nos casos encerrados.
- Retreino herda o viés do filtro.
- Incidente sem reconstituição de `short_circuit_layer` vs camada que elevou o risco.
- Degradação do XGBoost passa despercebida se ele quase nunca roda.
- Score `0` em camada skipped é mentira operacional.

## TO-BE: registro obrigatório por transação

Assíncrono (0 ms no orçamento síncrono):

```text
layers_executed
layers_skipped
short_circuit_layer
score_hbos          # null se não executou ou hbos_unavailable
score_xgb           # null se skipped ou xgb_unavailable
score_final
regras acionadas / signals
feature_weights
model_versions
decision_final
fallback_reason
```

Peso efetivo do HBOS, quando a política de cold start estiver ativa, entra no mesmo
registro para não confundir "HBOS não acusou" com "HBOS zerado".

`correlation_id` atravessa autorização, evento, workflow e notificação.

## TO-BE: shadow 1% a 5%

Avaliação assíncrona por **todas** as camadas, sem impactar o p95. Inclui os `deny` do HBOS
— é nesses casos que o viés de seleção do short-circuit se forma. Amostragem aleatória
reproduzível (semente de `transaction_id`). Publicação com `shadow_mode: true`; consumidores
operacionais filtram.

## Métricas e alertas

**Latência.** p50, p95, p99 total e por etapa contra o
[orçamento](../arquitetura/orcamento-de-latencia.md). Alerta se p95 total ≥ 90 ms ou etapa
≥ 80% do budget.

**Decisão.** Distribuição approve/challenge/deny; taxa de challenge; escore final.

**Cobertura de camada.** % de transações em que cada camada rodou. Queda abrupta = falha
silenciosa ou short-circuit indevido.

**Modelos.** `model_version_active` por instância; convergência < 5 min; divergência
HBOS/XGB; PSI/KS.

**Fallback.** Taxa por `hbos_unavailable` e `xgb_unavailable`. Fallback silencioso é o modo
de falha mais perigoso.

**Coorte.** Métricas quebradas por CPF novo vs demais, canal, região, tipo de
estabelecimento.

## Critérios de aceite

- 100% das transações com `layers_executed`, `layers_skipped`, `short_circuit_layer`.
- 100% das inferências com `model_version`.
- Score de camada skipped = `null` (teste).
- Shadow 1%–5% configurável, reprodutível, sem efeito no p95 (< 1 ms).
- Dashboard de convergência de versão e de divergência HBOS/XGB.
- Alerta de fallback acima do limite, por reason code.
- Zero CPF em claro em log/evento (teste).
- Caso reconstituível pelo `correlation_id`.
