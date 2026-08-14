# Operacionalização do `challenge` (Evolução prioritária 1)

## Lacuna/Risco (AS-IS)

A faixa `challenge` existe na lógica de decisão (`Decision.CHALLENGE`), mas, antes deste
trabalho, não havia fluxo operacional: um caso podia ser classificado como questionável sem
acionar fila, validação adicional, análise humana ou notificação.

## TO-BE implementado neste repositório

```text
DecisionCascade.decide() → challenge
  → AntifraudService.decide()
    → ChallengeOperationsService.handle_challenge_decision()
      → build_challenge_event()               (fraud.challenge.created)
      → ChallengeContextStore.save_context()  (idempotente por transaction_id+correlation_id)
      → ChallengeEventPublisher.publish()
      → TriageQueue.enqueue()

(worker separado, fora do hot path)
  → ChallengeOperationsService.process_next_in_triage()
    → ChallengeWorkflow.run()
      → AdditionalRulesValidator      (regras adicionais e calibração)
      → BlocklistBureauValidator      (se deny de alta confiança: encerra)
      → GeoDeviceValidator
      → ExtendedHistoryValidator
      → consolidação: approve / deny / escalate
    → NotificationService.notify()    (idempotente por chave transaction+correlation+decisão)
```

Módulos: `src/antifraud/challenge/` (`events.py`, `context_store.py`, `triage_queue.py`,
`validators.py`, `workflow.py`, `notifications.py`, `service.py`).

### Sequência da Evolução prioritária 1 — cobertura neste repositório

| # | Passo | Implementado | Observação |
|---|---|---|---|
| 1 | Publicação de evento para `challenge` | Sim | `ChallengeEventPublisher` (`InMemoryChallengeEventPublisher` para dev/teste) |
| 2 | Persistência de contexto/evidências | Sim | `ChallengeContextStore`, idempotente |
| 3 | Fila de triagem | Sim | `TriageQueue` (`InMemoryTriageQueue`) |
| 4 | Regras adicionais e calibração | Sim | `AdditionalRulesValidator` |
| 5 | Step-up de autenticação | Ponto de extensão (`step_up_hook`) | Não implementado; hook explícito em `ChallengeOperationsService` |
| 6 | Fila de análise humana para `escalate` | Parcial | `escalation_queue` opcional no `ChallengeOperationsService`; UI/operação humana fora de escopo |
| 7 | Notificação idempotente e rastreável | Sim | `NotificationService` |
| 8 | Integrações externas (bureau, blocklist, geo, device) | Stub | `BlocklistBureauValidator`/`GeoDeviceValidator` usam `event.context` local, não integrações reais |
| 9 | Agentes de IA assíncronos | **Não implementado** | Propositalmente fora de escopo — deve vir apenas após os controles determinísticos acima estarem operacionais em produção |

O `ChallengeWorkflow` reproduz o desenho lógico do Microsoft Agent Framework Workflows
(encadeamento de validadores, encerramento antecipado em deny de alta confiança, timeout,
circuit breaker, fallback seguro, checkpoints e idempotência), mas **não integra com o
framework real** — essa integração é uma evolução futura.

## Dados mínimos do evento `fraud.challenge.created`

Implementados em `ChallengeEvent` (`src/antifraud/domain/models.py`): `transaction_id`,
`correlation_id`, `cpf_token` (tokenizado via `tokenize_cpf`, nunca CPF em claro),
`timestamp`, `hbos_score`, `xgboost_score`, `consolidated_score`, `signals`,
`rule_evidences`, `features`, `model_versions`, `executed_layers`, `terminating_layer`,
`initial_decision`, `context` (inclui `is_cold_start` e `reason_codes`).

## Resiliência de cada validador

Cada `ValidatorStep` (`src/antifraud/challenge/workflow.py`) garante:

- **Timeout** configurável por validador (`ValidatorStep.timeout_seconds`), aplicado via
  `ThreadPoolExecutor` + `future.result(timeout=...)`.
- **Circuit breaker** por validador (`CircuitBreaker`): abre após N falhas consecutivas e
  passa a responder com fallback imediato (`ValidatorExecutionStatus.CIRCUIT_OPEN`).
- **Fallback seguro**: outcome configurável por passo (padrão `ESCALATE`), nunca bloqueia
  indefinidamente a decisão.
- **Registro de duração, resultado, erro, timeout e fallback**: todos presentes em
  `ValidatorResult`.

## Critérios de aceite (do contexto operacional) e cobertura de teste

- **100% dos casos `challenge` devem possuir desfecho rastreável** →
  `tests/test_challenge_idempotency.py::test_100_percent_of_challenge_cases_have_traceable_outcome`.
- **Toda decisão deve registrar evidências e reason codes** →
  `tests/test_challenge_event.py`, `tests/test_workflow_validators.py`.
- **Cada validador deve registrar duração, resultado, erro, timeout e fallback** →
  `tests/test_workflow_validators.py` (`test_each_validator_result_records_duration`,
  `test_slow_validator_times_out_and_uses_fallback`,
  `test_broken_validator_falls_back_safely_and_records_error`).
- **O fluxo deve ser idempotente por `transaction_id` e `correlation_id`** →
  `tests/test_challenge_idempotency.py` (publicação única + `workflow.run` idempotente).
- **Taxa de challenge/aprovação/negação/escalonamento monitorada**: **lacuna aberta** — este
  repositório expõe os dados brutos (traces, resultados de workflow) necessários para calcular
  essas taxas, mas não implementa o pipeline de métricas/dashboard em si (fora de escopo).
