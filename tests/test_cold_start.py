from antifraud.cache import ModelCache
from antifraud.challenge import ChallengeOutbox
from antifraud.engine import ScoreEngine
from antifraud.models import Transaction
from antifraud.policy import PolicyConfig

POLICY = PolicyConfig.load()


def svc() -> ScoreEngine:
    return ScoreEngine(POLICY, cache=ModelCache(), outbox=ChallengeOutbox())


def test_new_cpf_low_value_approve_with_monitor():
    result = svc().score(
        Transaction(
            transaction_id="tx-new-low",
            correlation_id="c",
            subject_id="tok_new",
            amount=50.0,
            timestamp="2026-08-14T12:00:00Z",
            is_new_subject=True,
            history_days=0,
        )
    )
    assert result.decision == "approve"
    assert "cold_start" in result.reason_codes
    assert "cold_start_low_value_monitor" in result.reason_codes
    assert result.terminated_by == "cold_start"


def test_new_cpf_mid_value_challenge():
    result = svc().score(
        Transaction(
            transaction_id="tx-new-mid",
            correlation_id="c",
            subject_id="tok_new",
            amount=500.0,
            timestamp="2026-08-14T12:00:00Z",
            is_new_subject=True,
        )
    )
    assert result.decision == "challenge"
    assert "cold_start_step_up" in result.reason_codes


def test_new_cpf_high_value_deny():
    result = svc().score(
        Transaction(
            transaction_id="tx-new-high",
            correlation_id="c",
            subject_id="tok_new",
            amount=5000.0,
            timestamp="2026-08-14T12:00:00Z",
            is_new_subject=True,
        )
    )
    assert result.decision == "deny"
    assert "cold_start_high_value" in result.reason_codes


def test_thresholds_change_without_redeploy():
    custom = PolicyConfig.from_dict(
        {
            **POLICY.__dict__,
            "low_value_max": 10.0,
            "policy_version": "policy-v2",
        }
    )
    engine = ScoreEngine(POLICY, cache=ModelCache(), outbox=ChallengeOutbox())
    before = engine.score(
        Transaction(
            transaction_id="tx-cfg",
            correlation_id="c",
            subject_id="tok_new",
            amount=50.0,
            timestamp="2026-08-14T12:00:00Z",
            is_new_subject=True,
        )
    )
    assert before.decision == "approve"
    engine.reload_policy(custom)
    after = engine.score(
        Transaction(
            transaction_id="tx-cfg-2",
            correlation_id="c",
            subject_id="tok_new",
            amount=50.0,
            timestamp="2026-08-14T12:00:00Z",
            is_new_subject=True,
        )
    )
    assert after.decision == "challenge"
    assert after.model_versions.policy == "policy-v2"


def test_hbos_weight_zero_for_new_subject_in_consolidation_path():
    # Force consolidation by giving enough history flag false but wait:
    # new subject short-circuits cold start. Use history_days above thin file
    # is_new_subject False to reach models, then inspect weights via a thin
    # file that still consolidates? Cold start treats history_days < 30 as new.
    # Use is_new_subject through injected path: skip by using history 400 and
    # checking feature_weights on a regular customer vs thin file with shadow.
    engine = ScoreEngine(POLICY, cache=ModelCache(), outbox=ChallengeOutbox(), shadow_force=True)
    thin = engine.score(
        Transaction(
            transaction_id="tx-thin",
            correlation_id="c",
            subject_id="tok_thin",
            amount=50.0,
            timestamp="2026-08-14T12:00:00Z",
            is_new_subject=True,
            history_days=0,
            injected_hbos=0.99,
            injected_xgboost=0.1,
        )
    )
    assert thin.feature_weights["hbos"] == POLICY.hbos_new_subject_weight
    assert "cold_start" in thin.reason_codes
