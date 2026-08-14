from __future__ import annotations

import pytest

from antifraud.api import V1_ALLOWED_KEYS, to_v1, to_v2
from antifraud.cache import ModelCache
from antifraud.challenge import ChallengeOutbox
from antifraud.engine import ScoreEngine
from antifraud.models import Transaction
from antifraud.policy import PolicyConfig

POLICY = PolicyConfig.load()


def engine(**kwargs) -> ScoreEngine:
    return ScoreEngine(POLICY, cache=ModelCache(), outbox=ChallengeOutbox(), **kwargs)


def tx(**overrides) -> Transaction:
    base = dict(
        transaction_id="tx-1",
        correlation_id="corr-1",
        subject_id="tok_abc",
        amount=50.0,
        timestamp="2026-08-14T12:00:00Z",
        history_days=400,
        is_new_subject=False,
    )
    base.update(overrides)
    return Transaction(**base)


class TestApiContracts:
    def test_v1_only_decision_final(self):
        result = engine().score(tx(injected_hbos=0.1, injected_xgboost=0.1))
        body = to_v1(result)
        assert set(body.keys()) <= V1_ALLOWED_KEYS
        assert body["decision_final"] in {"approve", "challenge", "deny"}
        assert "features" not in body
        assert "feature_weights" not in body
        assert "score" not in body

    def test_v2_requires_scope(self):
        result = engine().score(tx(injected_hbos=0.1, injected_xgboost=0.1))
        with pytest.raises(PermissionError):
            to_v2(result, scopes=[])

    def test_v2_masks_and_omits_features_without_scope(self):
        result = engine().score(tx(injected_hbos=0.1, injected_xgboost=0.1))
        body = to_v2(result, scopes=["score:read"])
        assert body["decision"] == result.decision
        assert "features" not in body
        assert "feature_weights" not in body
        assert not str(body.get("subject_id", "")).startswith("cpf:")
        assert "model_versions" in body

    def test_v2_features_need_extra_scope(self):
        result = engine().score(tx(injected_hbos=0.1, injected_xgboost=0.1))
        body = to_v2(result, scopes=["score:read", "explain:features", "explain:weights"])
        assert "features" in body
        assert "feature_weights" in body
