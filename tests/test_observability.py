from antifraud.cache import ModelCache
from antifraud.challenge import ChallengeOutbox
from antifraud.engine import ScoreEngine
from antifraud.models import Transaction
from antifraud.policy import PolicyConfig

POLICY = PolicyConfig.load()


def test_envelope_records_executed_and_skipped_layers():
    result = ScoreEngine(POLICY, cache=ModelCache(), outbox=ChallengeOutbox()).score(
        Transaction(
            transaction_id="tx-env",
            correlation_id="c",
            subject_id="tok",
            amount=20.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=400,
            critical_hard_rule=True,
        )
    )
    assert "hard_rules" in result.layers_executed
    assert "hbos" in result.layers_skipped
    assert result.terminated_by == "hard_rules"


def test_shadow_does_not_change_online_decision():
    engine = ScoreEngine(
        POLICY, cache=ModelCache(), outbox=ChallengeOutbox(), shadow_force=True
    )
    result = engine.score(
        Transaction(
            transaction_id="tx-shadow",
            correlation_id="c",
            subject_id="tok",
            amount=20.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=400,
            critical_hard_rule=True,
            injected_hbos=0.99,
            injected_xgboost=0.99,
        )
    )
    assert result.decision == "deny"
    assert result.terminated_by == "hard_rules"
    assert result.shadow_evaluated is True
    assert result.shadow_would_decide in {"approve", "challenge", "deny"}
    # High model scores in shadow must not override the hard-rule deny.
    assert result.decision == "deny"
