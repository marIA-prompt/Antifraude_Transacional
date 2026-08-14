from __future__ import annotations

from antifraud.challenge.context_store import InMemoryChallengeContextStore
from antifraud.challenge.events import InMemoryChallengeEventPublisher
from antifraud.challenge.service import ChallengeOperationsService
from antifraud.challenge.triage_queue import InMemoryTriageQueue
from antifraud.challenge.validators import AdditionalRulesValidator
from antifraud.challenge.workflow import ChallengeWorkflow, ValidatorStep
from antifraud.challenge.notifications import InMemoryNotificationSender, NotificationService
from antifraud.domain.models import DecisionTrace
from antifraud.domain.enums import Decision


def _build_service():
    context_store = InMemoryChallengeContextStore()
    publisher = InMemoryChallengeEventPublisher()
    triage_queue = InMemoryTriageQueue()
    workflow = ChallengeWorkflow(
        steps=[ValidatorStep(AdditionalRulesValidator())], context_store=context_store
    )
    notification_sender = InMemoryNotificationSender()
    notification_service = NotificationService(notification_sender)

    service = ChallengeOperationsService(
        publisher=publisher,
        context_store=context_store,
        triage_queue=triage_queue,
        workflow=workflow,
        notification_service=notification_service,
    )
    return service, publisher, triage_queue, notification_sender


def _trace(transaction_id="tx-1", correlation_id="corr-1") -> DecisionTrace:
    trace = DecisionTrace(
        transaction_id=transaction_id, correlation_id=correlation_id, decision=Decision.CHALLENGE
    )
    return trace


def test_duplicate_challenge_decision_is_not_republished():
    service, publisher, triage_queue, _ = _build_service()
    trace = _trace()

    service.handle_challenge_decision(trace, cpf="12345678900")
    service.handle_challenge_decision(trace, cpf="12345678900")

    assert len(publisher.published_events) == 1
    assert len(triage_queue) == 1


def test_100_percent_of_challenge_cases_have_traceable_outcome():
    service, _, _, notification_sender = _build_service()

    for i in range(5):
        trace = _trace(transaction_id=f"tx-{i}", correlation_id=f"corr-{i}")
        service.handle_challenge_decision(trace, cpf="12345678900")

    results = []
    while True:
        result = service.process_next_in_triage()
        if result is None:
            break
        results.append(result)

    assert len(results) == 5
    assert all(r.final_decision is not None for r in results)
    assert len(notification_sender.sent) == 5


def test_workflow_run_is_idempotent_by_transaction_and_correlation_id():
    service, _, _, _ = _build_service()
    trace = _trace()
    event = service.handle_challenge_decision(trace, cpf="12345678900")

    first = service.process_event(event)
    second = service.process_event(event)

    assert first.idempotency_replayed is False
    assert second.idempotency_replayed is True
    assert first.final_decision == second.final_decision
