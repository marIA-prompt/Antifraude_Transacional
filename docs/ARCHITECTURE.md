# Arquitetura do motor antifraude

Este documento resume a arquitetura implementada neste repositório e sua relação com o
contexto operacional completo em [`CONTEXTO_OPERACIONAL.md`](./CONTEXTO_OPERACIONAL.md).
Siga sempre a distinção **AS-IS / Lacuna-Risco / TO-BE / Critério de aceite**.

## AS-IS: fluxo de decisão em cascata

Implementado em `src/antifraud/decision/cascade.py` (`DecisionCascade.decide`):

```text
Transação
→ validação do payload            (antifraud.validation.payload)
→ cálculo de features             (antifraud.features.engine)
→ HBOS individual por CPF         (antifraud.models_ml.hbos)
→ hard rules                      (antifraud.rules.engine)
→ regras de negócio               (antifraud.rules.engine)
→ política de cold start          (antifraud.coldstart.policy)
→ XGBoost global                  (antifraud.models_ml.xgboost_model)
→ consolidação e decisão          (approve / challenge / deny / reject)
```

- **Short-circuit real**: uma hard rule crítica encerra a cascata imediatamente com `deny`,
  sem executar regras de negócio, política de cold start, XGBoost ou consolidação. Um payload
  inválido encerra tudo com `reject` (erro controlado, não é uma decisão de risco).
- **Observabilidade total**: cada execução produz um `DecisionTrace`
  (`antifraud.domain.models.DecisionTrace`) com as camadas executadas e não executadas,
  scores, sinais, regras, features, pesos e a camada que encerrou a decisão — isto mitiga
  exatamente o risco de "ocultar a performance das camadas posteriores" citado no contexto
  operacional. Todo trace é enviado a um `AuditSink` (`antifraud.audit.logger`),
  independentemente do que a API HTTP expõe.
- **Amostragem shadow**: `antifraud.decision.observability.ShadowSampler` marca uma fração
  configurável (1%-5%) das transações como amostra shadow. Este repositório apenas marca a
  amostra; a execução de todas as camadas em modo shadow para transações que sofreram
  short-circuit é responsabilidade de um processo assíncrono fora de escopo deste código.

## AS-IS: HBOS e XGBoost são interfaces, não modelos treinados

- `antifraud.models_ml.hbos.HbosScorer` + `HbosBundleCache`: interface de um score de anomalia
  por CPF. A implementação de referência (`InMemoryHbosBundleCache`) e o cálculo de score
  (z-score agregado) são **stubs determinísticos para permitir testar a cascata** — não é um
  modelo HBOS real treinado com dados históricos.
- `antifraud.models_ml.xgboost_model.XgboostScorer` (interface) + `StubXgboostScorer`
  (implementação de referência): o mesmo se aplica — nenhum modelo supervisionado é treinado
  neste repositório.
- **Lacuna/Risco**: sem um pipeline de treino real, validação temporal e rótulos maduros
  (ver `MLOPS_GOVERNANCE.md`), estes scores não devem ser usados para decisões de produção.
  Trate-os como pontos de extensão que devem ser substituídos por modelos versionados e
  publicados via o fluxo descrito em `MODEL_LIFECYCLE.md`.

## TO-BE: pontos de extensão para produção

| Componente AS-IS (stub) | Interface | Substituição TO-BE esperada |
|---|---|---|
| `InMemoryHbosBundleCache` | `HbosBundleCache` | Cache distribuído (Redis/Memcached) com invalidação por `model.published` |
| `StubXgboostScorer` | `XgboostScorer` | Modelo real treinado offline, versionado no model registry |
| `InMemoryCustomerProfileRepository` | `CustomerProfileRepository` | Feature store / data store transacional com histórico de até ~730 dias |
| `InMemoryChallengeEventPublisher` | `ChallengeEventPublisher` | Tópico de mensageria (Kafka, SNS/SQS, Service Bus) |
| `InMemoryChallengeContextStore` | `ChallengeContextStore` | Banco de auditoria persistente (idempotente por `transaction_id`+`correlation_id`) |
| `InMemoryTriageQueue` | `TriageQueue` | Fila gerenciada com DLQ, retry e priorização |
| `ChallengeWorkflow` (síncrono/local) | — | Integração real com Microsoft Agent Framework Workflows |
| `InMemoryNotificationSender` | `NotificationSender` | Canal real (webhook, push, e-mail) com garantia de entrega |

## Critério de aceite desta camada

- Toda transação processada por `DecisionCascade.decide` produz um `DecisionTrace` completo,
  mesmo quando o short-circuit é acionado (cobertura: `tests/test_cascade_short_circuit.py`).
- 100% das camadas do `Layer` enum aparecem no trace como executadas OU não executadas —
  nunca ausentes (cobertura: `tests/test_payload_validation.py::test_cascade_rejects_invalid_payload_with_reject_decision`).
- Toda decisão de hard rule é acompanhada de `reason_code` auditável
  (cobertura: `tests/test_rules_engine.py`, `tests/test_cascade_short_circuit.py`).
