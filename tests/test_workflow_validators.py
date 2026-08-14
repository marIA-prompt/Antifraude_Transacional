from __future__ import annotations

import time

from antifraud.challenge.context_store import InMemoryChallengeContextStore
from antifraud.challenge.validators import ChallengeValidator, ValidatorOutput
from antifraud.challenge.workflow import ChallengeWorkflow, ValidatorStep
from antifraud.domain.enums import Decision, ValidatorExecutionStatus, ValidatorOutcome
from antifraud.domain.models import ChallengeEvent


def _event(transaction_id="tx-1", correlation_id="corr-1") -> ChallengeEvent:
    return ChallengeEvent(
        transaction_id=transaction_id,
        correlation_id=correlation_id,
        cpf_token="cpf_tok_abc",
        consolidated_score=0.5,
    )


class ApproveValidator(ChallengeValidator):
    name = "approve_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        return ValidatorOutput(outcome=ValidatorOutcome.APPROVE)


class HighConfidenceDenyValidator(ChallengeValidator):
    name = "deny_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        return ValidatorOutput(
            outcome=ValidatorOutcome.DENY, reason_codes=["bureau_hit"], high_confidence=True
        )


class SlowValidator(ChallengeValidator):
    name = "slow_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        time.sleep(1.0)
        return ValidatorOutput(outcome=ValidatorOutcome.APPROVE)


class BrokenValidator(ChallengeValidator):
    name = "broken_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        raise RuntimeError("integração externa indisponível")


def test_workflow_consolidates_approve_when_all_validators_approve():
    workflow = ChallengeWorkflow(
        steps=[ValidatorStep(ApproveValidator())],
        context_store=InMemoryChallengeContextStore(),
    )
    result = workflow.run(_event())
    assert result.final_decision == Decision.APPROVE
    assert result.validator_results[0].execution_status == ValidatorExecutionStatus.OK


def test_high_confidence_deny_short_circuits_remaining_validators():
    workflow = ChallengeWorkflow(
        steps=[ValidatorStep(HighConfidenceDenyValidator()), ValidatorStep(ApproveValidator())],
        context_store=InMemoryChallengeContextStore(),
    )
    result = workflow.run(_event())

    assert result.final_decision == Decision.DENY
    assert len(result.validator_results) == 1
    assert result.validator_results[0].validator_name == "deny_validator"
    assert "bureau_hit" in result.reason_codes


def test_slow_validator_times_out_and_uses_fallback():
    workflow = ChallengeWorkflow(
        steps=[ValidatorStep(SlowValidator(), timeout_seconds=0.05)],
        context_store=InMemoryChallengeContextStore(),
    )
    result = workflow.run(_event())

    validator_result = result.validator_results[0]
    assert validator_result.execution_status == ValidatorExecutionStatus.TIMEOUT
    assert validator_result.used_fallback is True
    assert "timeout" in validator_result.reason_codes
    # Fallback é seguro (ESCALATE por padrão), nunca bloqueia indefinidamente a decisão.
    assert result.final_decision == Decision.ESCALATE


def test_broken_validator_falls_back_safely_and_records_error():
    workflow = ChallengeWorkflow(
        steps=[ValidatorStep(BrokenValidator())],
        context_store=InMemoryChallengeContextStore(),
    )
    result = workflow.run(_event())

    validator_result = result.validator_results[0]
    assert validator_result.execution_status == ValidatorExecutionStatus.ERROR
    assert validator_result.error is not None
    assert validator_result.used_fallback is True


def test_circuit_breaker_opens_after_repeated_failures_and_short_circuits_validator():
    workflow = ChallengeWorkflow(
        steps=[ValidatorStep(BrokenValidator())],
        context_store=InMemoryChallengeContextStore(),
    )
    # Três eventos distintos para não colidir com a idempotência do workflow.
    for i in range(3):
        workflow.run(_event(transaction_id=f"tx-{i}", correlation_id=f"corr-{i}"))

    result = workflow.run(_event(transaction_id="tx-final", correlation_id="corr-final"))
    validator_result = result.validator_results[0]
    assert validator_result.execution_status == ValidatorExecutionStatus.CIRCUIT_OPEN


def test_each_validator_result_records_duration():
    workflow = ChallengeWorkflow(
        steps=[ValidatorStep(ApproveValidator())],
        context_store=InMemoryChallengeContextStore(),
    )
    result = workflow.run(_event())
    assert result.validator_results[0].duration_ms >= 0.0
