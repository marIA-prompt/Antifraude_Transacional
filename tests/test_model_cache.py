import pytest

from antifraud.cache import Artifact, IncompatibleFeatureSchema, ModelCache
from antifraud.challenge import ChallengeOutbox
from antifraud.engine import ScoreEngine
from antifraud.models import Transaction
from antifraud.policy import PolicyConfig


def test_publish_swaps_pointer_without_restart():
    cache = ModelCache()
    old = cache.active_version("xgboost")
    published = cache.publish(
        Artifact("xgboost", "xgb-2", "features-v1", b"xgb-2-bytes", state="champion")
    )
    assert published.version == "xgb-2"
    assert cache.active_version("xgboost") == "xgb-2"
    assert cache.active_version("xgboost") != old


def test_incompatible_schema_rejected():
    cache = ModelCache()
    with pytest.raises(IncompatibleFeatureSchema):
        cache.publish(Artifact("xgboost", "xgb-x", "features-v0", b"x", state="champion"))


def test_rollback_restores_previous_champion():
    cache = ModelCache()
    original = cache.active_version("hbos")
    cache.publish(Artifact("hbos", "hbos-9", "features-v1", b"hbos-9", state="champion"))
    cache.rollback("hbos")
    assert cache.active_version("hbos") == original


def test_every_inference_records_model_version():
    cache = ModelCache()
    cache.publish(Artifact("hbos", "hbos-live", "features-v1", b"h", state="champion"))
    cache.publish(Artifact("xgboost", "xgb-live", "features-v1", b"x", state="champion"))
    svc = ScoreEngine(PolicyConfig.load(), cache=cache, outbox=ChallengeOutbox())
    result = svc.score(
        Transaction(
            transaction_id="tx-v",
            correlation_id="corr-v",
            subject_id="tok_v",
            amount=40.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=200,
            injected_hbos=0.1,
            injected_xgboost=0.1,
        )
    )
    assert result.model_versions.hbos == "hbos-live"
    assert result.model_versions.xgboost == "xgb-live"
    assert result.model_versions.policy == PolicyConfig.load().policy_version


def test_stale_instances_are_listed():
    cache = ModelCache()
    cache.mark_stale("pod-a")
    cache.mark_stale("pod-a")
    assert cache.stale_instances == ["pod-a"]
