from __future__ import annotations

from antifraud.api.app import build_default_antifraud_service
from antifraud.domain.enums import Decision
from tests.conftest import make_payload


def test_challenge_decision_triggers_event_publication_and_triage_enqueue():
    service = build_default_antifraud_service()
    payload = make_payload(
        transaction_id="tx-300",
        correlation_id="corr-300",
        cpf="55555555555",
        amount=1000.0,
    )

    result = service.decide(payload)

    assert result.decision == Decision.CHALLENGE
    published = service._challenge_service._publisher.published_events
    assert len(published) == 1
    assert published[0].transaction_id == "tx-300"
    assert len(service._challenge_service._triage_queue) == 1


def test_non_challenge_decision_does_not_publish_event():
    service = build_default_antifraud_service()
    payload = make_payload(
        transaction_id="tx-301", correlation_id="corr-301", cpf="66666666666", amount=50.0
    )

    result = service.decide(payload)

    assert result.decision == Decision.APPROVE
    assert len(service._challenge_service._publisher.published_events) == 0


def test_every_decision_is_recorded_in_audit_sink():
    service = build_default_antifraud_service()
    payload = make_payload(transaction_id="tx-302", correlation_id="corr-302")

    service.decide(payload)

    trace = service._audit_sink.find("tx-302", "corr-302")
    assert trace is not None
    assert trace.decision is not None
