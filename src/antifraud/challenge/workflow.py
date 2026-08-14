from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field

from antifraud.challenge.context_store import ChallengeContextStore
from antifraud.challenge.validators import ChallengeValidator, ValidatorOutput
from antifraud.domain.enums import Decision, ValidatorExecutionStatus, ValidatorOutcome
from antifraud.domain.models import ChallengeEvent, ValidatorResult, WorkflowResult


@dataclass
class CircuitBreakerState:
    failure_count: int = 0
    open: bool = False
    failure_threshold: int = 3


class CircuitBreaker:
    """Circuit breaker simples por validador (fecha após N falhas consecutivas)."""

    def __init__(self, failure_threshold: int = 3):
        self._states: dict[str, CircuitBreakerState] = {}
        self._failure_threshold = failure_threshold

    def _state_for(self, validator_name: str) -> CircuitBreakerState:
        return self._states.setdefault(
            validator_name, CircuitBreakerState(failure_threshold=self._failure_threshold)
        )

    def is_open(self, validator_name: str) -> bool:
        return self._state_for(validator_name).open

    def record_success(self, validator_name: str) -> None:
        state = self._state_for(validator_name)
        state.failure_count = 0
        state.open = False

    def record_failure(self, validator_name: str) -> None:
        state = self._state_for(validator_name)
        state.failure_count += 1
        if state.failure_count >= state.failure_threshold:
            state.open = True

    def reset(self, validator_name: str) -> None:
        self._states.pop(validator_name, None)


@dataclass
class ValidatorStep:
    validator: ChallengeValidator
    timeout_seconds: float = 2.0
    fallback_outcome: ValidatorOutcome = ValidatorOutcome.ESCALATE
    fallback_reason_code: str = "validator_fallback"


@dataclass
class WorkflowCheckpoint:
    """Estado intermediário do workflow, para retomada em integrações externas lentas."""

    transaction_id: str
    correlation_id: str
    completed_validator_names: list[str] = field(default_factory=list)
    validator_results: list[ValidatorResult] = field(default_factory=list)


class ChallengeWorkflow:
    """Orquestrador dos validadores do challenge (equivalente ao Agent Framework Workflows).

    Implementação de referência síncrona/local: reproduz o desenho lógico
    (encadeamento de validadores com encerramento antecipado em deny de
    alta confiança, timeout, circuit breaker, fallback seguro,
    idempotência e checkpoints), mas não integra com o Microsoft Agent
    Framework Workflows real -- essa integração é uma evolução futura fora
    de escopo deste código.
    """

    def __init__(
        self,
        steps: list[ValidatorStep],
        context_store: ChallengeContextStore,
        executor: concurrent.futures.Executor | None = None,
    ) -> None:
        self._steps = steps
        self._context_store = context_store
        self._circuit_breaker = CircuitBreaker()
        self._executor = executor or concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._results_by_key: dict[str, WorkflowResult] = {}
        self._checkpoints: dict[str, WorkflowCheckpoint] = {}

    def run(self, event: ChallengeEvent) -> WorkflowResult:
        key = f"{event.transaction_id}:{event.correlation_id}"
        if key in self._results_by_key:
            previous = self._results_by_key[key]
            return previous.model_copy(update={"idempotency_replayed": True})

        checkpoint = self._checkpoints.setdefault(
            key,
            WorkflowCheckpoint(
                transaction_id=event.transaction_id, correlation_id=event.correlation_id
            ),
        )

        all_reason_codes: list[str] = [
            rc for r in checkpoint.validator_results for rc in r.reason_codes
        ]
        final_decision: Decision | None = None

        for step in self._steps:
            if step.validator.name in checkpoint.completed_validator_names:
                continue

            result = self._run_step(step, event)
            checkpoint.validator_results.append(result)
            checkpoint.completed_validator_names.append(step.validator.name)
            all_reason_codes.extend(result.reason_codes)

            if (
                result.outcome == ValidatorOutcome.DENY
                and result.evidence.get("high_confidence")
            ):
                final_decision = Decision.DENY
                break

        if final_decision is None:
            final_decision = self._consolidate(checkpoint.validator_results)

        workflow_result = WorkflowResult(
            transaction_id=event.transaction_id,
            correlation_id=event.correlation_id,
            final_decision=final_decision,
            validator_results=checkpoint.validator_results,
            reason_codes=all_reason_codes,
        )
        self._results_by_key[key] = workflow_result
        return workflow_result

    def _run_step(self, step: ValidatorStep, event: ChallengeEvent) -> ValidatorResult:
        name = step.validator.name
        if self._circuit_breaker.is_open(name):
            return ValidatorResult(
                validator_name=name,
                contract_version=step.validator.contract_version,
                outcome=step.fallback_outcome,
                execution_status=ValidatorExecutionStatus.CIRCUIT_OPEN,
                reason_codes=[step.fallback_reason_code, "circuit_open"],
                used_fallback=True,
            )

        start = time.perf_counter()
        future = self._executor.submit(step.validator.validate, event)
        try:
            output: ValidatorOutput = future.result(timeout=step.timeout_seconds)
        except concurrent.futures.TimeoutError:
            self._circuit_breaker.record_failure(name)
            duration_ms = round((time.perf_counter() - start) * 1000, 4)
            return ValidatorResult(
                validator_name=name,
                contract_version=step.validator.contract_version,
                outcome=step.fallback_outcome,
                execution_status=ValidatorExecutionStatus.TIMEOUT,
                duration_ms=duration_ms,
                reason_codes=[step.fallback_reason_code, "timeout"],
                used_fallback=True,
            )
        except Exception as exc:  # noqa: BLE001 - fallback seguro deliberado
            self._circuit_breaker.record_failure(name)
            duration_ms = round((time.perf_counter() - start) * 1000, 4)
            return ValidatorResult(
                validator_name=name,
                contract_version=step.validator.contract_version,
                outcome=step.fallback_outcome,
                execution_status=ValidatorExecutionStatus.ERROR,
                duration_ms=duration_ms,
                reason_codes=[step.fallback_reason_code, "validator_error"],
                error=str(exc),
                used_fallback=True,
            )

        self._circuit_breaker.record_success(name)
        duration_ms = round((time.perf_counter() - start) * 1000, 4)
        evidence = dict(output.evidence)
        if output.high_confidence:
            evidence["high_confidence"] = True
        return ValidatorResult(
            validator_name=name,
            contract_version=step.validator.contract_version,
            outcome=output.outcome,
            execution_status=ValidatorExecutionStatus.OK,
            duration_ms=duration_ms,
            reason_codes=output.reason_codes,
            evidence=evidence,
        )

    @staticmethod
    def _consolidate(results: list[ValidatorResult]) -> Decision:
        outcomes = [r.outcome for r in results if r.outcome is not None]
        if any(o == ValidatorOutcome.DENY for o in outcomes):
            return Decision.DENY
        if any(o == ValidatorOutcome.ESCALATE for o in outcomes):
            return Decision.ESCALATE
        return Decision.APPROVE
