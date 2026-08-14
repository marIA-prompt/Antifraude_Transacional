# 05 — Operacionalização do `challenge`

Prioridade 1 da evolução. Agentes de IA **não** entram nesta fase.

## AS-IS

- Motor emite `challenge` como faixa.
- Produto, no recorte da Regra 83, dispara confirmação via WhatsApp.
- Não há garantia de fila, desfecho, escalate, idempotência nem evidência por
  validador para 100% dos challenges.

## Lacuna / risco

Caso questionável sem ação: autorização implícita, negação opaca ou limbo.
WhatsApp não cobre challenges originados por HBOS/XGBoost/cold start.

## TO-BE — sequência de implementação

| Fase | Entrega | Ainda não é |
| --- | --- | --- |
| 1 | Publicar `fraud.challenge.created` | Workflow |
| 2 | Persistir contexto + evidências (outbox) | Integrações externas |
| 3 | Fila de triagem idempotente | Agentes |
| 4 | Regras adicionais e calibração | Bureau |
| 5 | Step-up (WhatsApp ou outro canal) quando aplicável | Substituição das hard rules |
| 6 | Fila humana para `escalate` | AutoML |
| 7 | Notificação idempotente | — |
| 8 | Bureau, blocklist, geo, device | — |
| 9 | Agentes assíncronos de apoio | Decisão crítica autônoma |

Fluxo alvo:

```text
ML + regras
→ challenge
→ evento fraud.challenge.created
→ persistência + fila (outbox)
→ validadores interligados (planejado: Agent Framework Workflows)
→ approve / deny / escalate
→ notificação sim/não
→ auditoria
```

## Contrato do evento

Schema: [`contracts/events/fraud.challenge.created.schema.json`](../contracts/events/fraud.challenge.created.schema.json)

Campos mínimos:

```text
transaction_id
correlation_id
subject_id (CPF tokenizado — nunca CPF em claro)
timestamp
score_hbos
score_xgboost
score_consolidated
signals[] / rules_triggered[]
features_relevant
model_versions
layers_executed
terminated_by
initial_decision = challenge
validator_context
```

Evento de desfecho: [`fraud.challenge.resolved.schema.json`](../contracts/events/fraud.challenge.resolved.schema.json).

## Validadores (desenho, não produção)

Contrato de cada validador:

| Campo | Descrição |
| --- | --- |
| `validator_id` / `version` | Identidade |
| `decision` | `approve` \| `deny` \| `escalate` |
| `reason_codes` / `evidence` | Auditáveis |
| `duration_ms` | Latência |
| `error` / `timeout` / `fallback` | Observabilidade |

Regras de execução:

- timeout e circuit breaker obrigatórios;
- fallback seguro (em dúvida, `escalate`, nunca approve silencioso em alto valor);
- short-circuit de `deny` de alta confiança;
- checkpoints para step-up e integrações lentas;
- testável isoladamente.

Ordem planejada:

```text
regras adicionais
→ blocklist / bureau
→ geo / device
→ histórico estendido
→ consolidação
→ (futuro) agente de triagem
```

WhatsApp de confirmação é o step-up da fase 5, não o validador único.

## Critérios de aceite

- 100% dos `challenge` do motor geram exatamente um evento de criação (idempotente).
- 100% possuem desfecho `approve` / `deny` / `escalate` rastreável em janela SLA.
- Cada validador registra duração, resultado, erro, timeout e fallback.
- Idempotência por `transaction_id` + `correlation_id`.
- Métricas: taxa de challenge, aprovação posterior, negação posterior, escalate.
- Testes: `tests/test_challenge_outbox.py`.
