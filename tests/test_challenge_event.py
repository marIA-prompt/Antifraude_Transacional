from __future__ import annotations

from antifraud.challenge.events import build_challenge_event, tokenize_cpf
from antifraud.domain.enums import Decision, Layer
from antifraud.domain.models import ModelScore
from tests.conftest import make_payload


def test_tokenize_cpf_is_deterministic_and_irreversible():
    token1 = tokenize_cpf("12345678900")
    token2 = tokenize_cpf("12345678900")
    token3 = tokenize_cpf("00000000000")

    assert token1 == token2
    assert token1 != token3
    assert "12345678900" not in token1


def test_build_challenge_event_contains_minimum_required_fields(cascade):
    payload = make_payload(amount=1500.0, cpf="99999999999")
    result = cascade.decide(payload)

    event = build_challenge_event(result.trace, payload.cpf)

    assert event.event_name == "fraud.challenge.created"
    assert event.transaction_id == payload.transaction_id
    assert event.correlation_id == payload.correlation_id
    assert event.cpf_token == tokenize_cpf(payload.cpf)
    assert event.xgboost_score is not None
    assert isinstance(event.executed_layers, list) and len(event.executed_layers) > 0
    assert event.terminating_layer is not None
    assert "reason_codes" in event.context
    assert "is_cold_start" in event.context


def test_challenge_event_never_leaks_raw_cpf():
    from antifraud.domain.models import DecisionTrace

    trace = DecisionTrace(
        transaction_id="tx-1",
        correlation_id="corr-1",
        hbos_score=ModelScore(model_name="hbos_individual", model_version="v1", score=0.5),
        xgboost_score=ModelScore(model_name="xgboost_global", model_version="v1", score=0.5),
        decision=Decision.CHALLENGE,
    )
    trace.terminating_layer = Layer.CONSOLIDATION

    event = build_challenge_event(trace, cpf="12345678900")
    serialized = event.model_dump_json()
    assert "12345678900" not in serialized
