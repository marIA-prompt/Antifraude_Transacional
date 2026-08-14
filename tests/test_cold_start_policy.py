from __future__ import annotations

from antifraud.coldstart.policy import ColdStartPolicy, ColdStartThresholds
from antifraud.domain.enums import Decision
from tests.conftest import make_payload


def test_not_cold_start_returns_no_hint():
    policy = ColdStartPolicy()
    payload = make_payload(amount=100.0)
    hint = policy.evaluate(payload, is_cold_start=False, has_critical_hard_rule=False)
    assert hint.is_cold_start is False
    assert hint.suggested_decision is None


def test_cold_start_low_value_suggests_approve_with_monitoring():
    policy = ColdStartPolicy(ColdStartThresholds(low_value_ceiling=200.0, high_value_floor=3000.0))
    payload = make_payload(amount=50.0)
    hint = policy.evaluate(payload, is_cold_start=True, has_critical_hard_rule=False)
    assert hint.suggested_decision == Decision.APPROVE
    assert "cold_start" in hint.reason_codes
    assert "cold_start_low_value_monitored" in hint.reason_codes


def test_cold_start_intermediate_value_suggests_challenge():
    policy = ColdStartPolicy(ColdStartThresholds(low_value_ceiling=200.0, high_value_floor=3000.0))
    payload = make_payload(amount=1000.0)
    hint = policy.evaluate(payload, is_cold_start=True, has_critical_hard_rule=False)
    assert hint.suggested_decision == Decision.CHALLENGE
    assert "cold_start_intermediate_value_stepup" in hint.reason_codes


def test_cold_start_high_value_suggests_escalate():
    policy = ColdStartPolicy(ColdStartThresholds(low_value_ceiling=200.0, high_value_floor=3000.0))
    payload = make_payload(amount=5000.0)
    hint = policy.evaluate(payload, is_cold_start=True, has_critical_hard_rule=False)
    assert hint.suggested_decision == Decision.ESCALATE


def test_cold_start_with_critical_hard_rule_denies():
    policy = ColdStartPolicy()
    payload = make_payload(amount=50.0)
    hint = policy.evaluate(payload, is_cold_start=True, has_critical_hard_rule=True)
    assert hint.suggested_decision == Decision.DENY
    assert "cold_start_hard_rule" in hint.reason_codes


def test_cold_start_reduces_hbos_weight_and_boosts_global_model():
    thresholds = ColdStartThresholds(hbos_weight_reduction_factor=0.0, global_model_weight_boost=1.5)
    policy = ColdStartPolicy(thresholds)
    payload = make_payload(amount=50.0)
    hint = policy.evaluate(payload, is_cold_start=True, has_critical_hard_rule=False)
    assert hint.hbos_weight_multiplier == 0.0
    assert hint.global_model_weight_multiplier == 1.5


def test_cascade_applies_cold_start_policy_for_new_cpf(cascade):
    payload = make_payload(cpf="99999999999", amount=50.0)
    result = cascade.decide(payload)

    assert result.trace.is_cold_start is True
    assert "cold_start" in result.trace.reason_codes
    assert result.decision == Decision.APPROVE
