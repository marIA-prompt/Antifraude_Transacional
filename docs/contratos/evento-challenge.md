# Contrato do evento `fraud.challenge.created`

Schema normativo:
[`contracts/events/fraud.challenge.created.schema.json`](../../contracts/events/fraud.challenge.created.schema.json)

## AS-IS

A banda `challenge` existe na decisão online. **Não** há publicação deste evento em
produção. A HTTP v1 expõe só `decision_final`.

## Lacuna/Risco

Transação questionável pode não acionar fila, step-up, análise humana ou notificação. Um
orquestrador na HTTP v1 não teria score, sinais, features nem versões.

## TO-BE

O orquestrador **não depende da resposta HTTP**. Recebe contexto por este evento interno,
publicado de forma assíncrona (0 ms no orçamento síncrono).

```text
ML + regras → challenge
→ evento fraud.challenge.created
→ fila de triagem
→ Agent Framework Workflows   # evolução, não produção
→ validadores interligados
→ approve / deny / escalate
→ notificação sim/não
→ auditoria
```

Agent Framework Workflows permanece restrito a esta esteira. Não está em produção.

### Contrato versionado e idempotente

Campos mínimos do briefing. O schema executável adiciona `event_id` (unicidade da entrega)
e campos opcionais de rastreio (`layers_skipped`, `fallback_reason`, `shadow_mode`).

`idempotency_key` = `transaction_id` + `:` + `schema_version`. Consumidores tratam
reentrega como a mesma unidade de trabalho. `event_id` identifica a entrega, não o caso.

`cpf_token` é identificador tokenizado. **CPF em claro não trafega.**

`ttl_seconds` padrão de referência: **900**. Caso sem desfecho após o TTL entra em
conciliação (não some).

`short_circuit_layer` é `null` quando todas as camadas previstas rodaram até a
consolidação; `hbos` quando o deny do HBOS encerrou (neste caso o evento de challenge
**não** deveria ser publicado — challenge não nasce de short-circuit de deny). O campo
existe no contrato genérico de rastreio para o log; no tópico `fraud.challenge.created`
espera-se `null` ou camada que elevou à banda intermediária.

`signals` no briefing é lista de códigos (`valor_acima_padrao`, `estabelecimento_novo`).
O schema preserva essa forma (array de strings). Evidência estruturada, se necessária aos
validadores, vai em `features` minimizadas.

Scores: `hbos`, `xgb`, `final`. Camada não executada → `null`, nunca `0`.

Thresholds: `approve_max` e `deny_min` (referência do briefing: 0,40 e 0,70 — valores de
exemplo, versionáveis).

## Exemplo

```json
{
  "event": "fraud.challenge.created",
  "schema_version": "1.0",
  "event_id": "6f9619ff-8b86-d011-b42d-00cf4fc964ff",
  "idempotency_key": "txn-9912834:1.0",
  "transaction_id": "txn-9912834",
  "correlation_id": "corr-4471a",
  "cpf_token": "tok_7f3c1a9e",
  "occurred_at": "2026-08-13T11:36:00-03:00",
  "decision_initial": "challenge",
  "scores": {
    "hbos": 0.62,
    "xgb": 0.48,
    "final": 0.55
  },
  "thresholds": {
    "approve_max": 0.40,
    "deny_min": 0.70
  },
  "signals": ["valor_acima_padrao", "estabelecimento_novo", "cold_start"],
  "features": {
    "valor_normalizado": 0.82,
    "estabelecimento_novo_para_titular": 1
  },
  "feature_weights": {
    "valor_normalizado": 0.31
  },
  "model_versions": {
    "hbos": "cpf/tok_7f3c1a9e/v12",
    "xgb": "global/v7"
  },
  "layers_executed": ["validacao", "features", "hbos", "rules", "xgb"],
  "layers_skipped": [],
  "short_circuit_layer": null,
  "fallback_reason": null,
  "ttl_seconds": 900,
  "shadow_mode": false,
  "feature_schema_version": "features:candidate-2026.08.25"
}
```

`feature_schema_version` usa `features:candidate-2026.08.25` enquanto D-2 não estiver
`reconciled`. Não copiar o número 10 ou 13 para este campo.

## Critérios de aceite

- **100%** das transações `challenge` (não shadow) publicam o evento, validado contra o
  schema antes da publicação.
- Publicação fora do caminho síncrono; acréscimo ao p95 do fast path < 1 ms.
- Conciliação: nenhum `challenge` sem evento correspondente.
- Reentrega não duplica caso, validador nem notificação (teste de idempotência).
- Nenhum campo com CPF em claro (teste automatizado).
- Eventos com `shadow_mode: true` não entram na fila operacional (teste do consumidor).
