from __future__ import annotations

from antifraud.domain.enums import Decision, Layer
from tests.conftest import make_payload


def test_hard_rule_short_circuits_remaining_layers(cascade):
    payload = make_payload(extra={"blocklisted": True})
    result = cascade.decide(payload)

    assert result.decision == Decision.DENY
    assert result.trace.terminating_layer == Layer.HARD_RULES
    assert "blocklist_match" in result.trace.reason_codes

    executed = set(result.trace.executed_layers())
    skipped = set(result.trace.skipped_layers())

    assert Layer.HBOS_INDIVIDUAL in executed
    assert Layer.HARD_RULES in executed
    assert Layer.BUSINESS_RULES in skipped
    assert Layer.XGBOOST_GLOBAL in skipped
    assert Layer.CONSOLIDATION in skipped


def test_full_flow_executes_all_layers_when_no_hard_rule(cascade):
    payload = make_payload(amount=120.0)
    result = cascade.decide(payload)

    executed = set(result.trace.executed_layers())
    assert executed == set(Layer)
    assert result.trace.consolidated_score is not None
    assert result.decision in {Decision.APPROVE, Decision.CHALLENGE, Decision.DENY}


def test_decision_trace_always_records_scores_and_versions(cascade):
    payload = make_payload(amount=500.0)
    result = cascade.decide(payload)

    assert result.trace.hbos_score is not None
    assert result.trace.hbos_score.model_version == "hbos-v1"
    assert result.trace.xgboost_score is not None
    assert result.trace.xgboost_score.model_version.startswith("xgb-stub")
