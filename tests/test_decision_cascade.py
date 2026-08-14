from antifraud.cache import ModelCache
from antifraud.challenge import ChallengeOutbox
from antifraud.engine import PayloadValidationError, ScoreEngine
from antifraud.models import Transaction
from antifraud.policy import PolicyConfig
import pytest

POLICY = PolicyConfig.load()


def svc(**kwargs) -> ScoreEngine:
    return ScoreEngine(POLICY, cache=ModelCache(), outbox=ChallengeOutbox(), **kwargs)


def test_critical_hard_rule_prevails_over_low_scores():
    result = svc().score(
        Transaction(
            transaction_id="tx-hr",
            correlation_id="c",
            subject_id="tok",
            amount=20.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=400,
            critical_hard_rule=True,
            injected_hbos=0.01,
            injected_xgboost=0.01,
        )
    )
    assert result.decision == "deny"
    assert result.terminated_by == "hard_rules"
    assert "hard_rule_critical" in result.reason_codes
    assert "hbos" in result.layers_skipped
    assert "xgboost" in result.layers_skipped


def test_hbos_alone_does_not_deny():
    aggressive = PolicyConfig.from_dict(
        {
            **POLICY.__dict__,
            "hbos_weight": 0.9,
            "xgboost_weight": 0.1,
        }
    )
    result = ScoreEngine(
        aggressive, cache=ModelCache(), outbox=ChallengeOutbox()
    ).score(
        Transaction(
            transaction_id="tx-hbos",
            correlation_id="c",
            subject_id="tok",
            amount=80.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=400,
            injected_hbos=0.99,
            injected_xgboost=0.05,
        )
    )
    assert result.decision == "challenge"
    assert "hbos_signal_not_fraud_proof" in result.reason_codes
    assert result.decision != "deny"


def test_rule_83_not_triggered_does_not_auto_approve():
    result = svc().score(
        Transaction(
            transaction_id="tx-83-no",
            correlation_id="c",
            subject_id="tok",
            amount=80.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=400,
            rule_83_candidate=False,
            injected_hbos=0.2,
            injected_xgboost=0.95,
        )
    )
    assert "rule_83_not_triggered" in result.signals
    assert result.decision == "deny"


def test_rule_83_triggered_is_signal_not_whatsapp():
    result = svc().score(
        Transaction(
            transaction_id="tx-83-yes",
            correlation_id="c",
            subject_id="tok",
            amount=80.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=400,
            rule_83_candidate=True,
            injected_hbos=0.1,
            injected_xgboost=0.1,
        )
    )
    assert "rule_83_triggered" in result.signals
    assert result.decision == "approve"


def test_invalid_payload_is_controlled_error():
    with pytest.raises(PayloadValidationError) as err:
        svc().score(
            Transaction(
                transaction_id="",
                correlation_id="c",
                subject_id="tok",
                amount=10,
                timestamp="2026-08-14T12:00:00Z",
            )
        )
    assert err.value.reason_code == "invalid_payload"


def test_cpf_in_subject_rejected():
    with pytest.raises(PayloadValidationError) as err:
        svc().score(
            Transaction(
                transaction_id="tx",
                correlation_id="c",
                subject_id="cpf:00000000000",
                amount=10,
                timestamp="2026-08-14T12:00:00Z",
            )
        )
    assert err.value.reason_code == "lgpd_cpf_forbidden"
