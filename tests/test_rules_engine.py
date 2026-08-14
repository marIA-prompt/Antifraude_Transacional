from __future__ import annotations

from datetime import datetime, timezone

from antifraud.rules.engine import default_rules_engine
from tests.conftest import make_payload


def test_hard_rule_blocklist_triggers():
    engine = default_rules_engine()
    payload = make_payload(extra={"blocklisted": True})
    evidence = engine.evaluate_hard_rules(payload, features={})
    assert evidence is not None
    assert evidence.is_hard_rule is True
    assert evidence.reason_code == "blocklist_match"


def test_hard_rule_impossible_travel_triggers():
    engine = default_rules_engine()
    payload = make_payload(extra={"impossible_travel": True})
    evidence = engine.evaluate_hard_rules(payload, features={})
    assert evidence is not None
    assert evidence.reason_code == "impossible_travel"


def test_no_hard_rule_when_clean():
    engine = default_rules_engine()
    payload = make_payload()
    evidence = engine.evaluate_hard_rules(payload, features={})
    assert evidence is None


def test_business_rules_accumulate_evidence():
    engine = default_rules_engine()
    payload = make_payload(
        amount=6000.0,
        merchant_is_new=True,
        installments=12,
        timestamp=datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc),
    )
    evidences = engine.evaluate_business_rules(payload, features={})
    reason_codes = {e.reason_code for e in evidences}
    assert "high_value_new_merchant" in reason_codes
    assert "high_installments" in reason_codes
    assert "odd_hour_high_value" in reason_codes
    assert all(not e.is_hard_rule for e in evidences)
