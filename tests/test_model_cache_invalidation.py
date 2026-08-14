from __future__ import annotations

import pytest

from antifraud.models_ml.cache import (
    InstanceModelVersionTracker,
    ModelCacheInvalidationService,
    ModelPublishedEvent,
)
from antifraud.models_ml.hbos import HbosBundle, InMemoryHbosBundleCache
from antifraud.models_ml.registry import ModelRegistry, ModelRegistryError, ModelRegistryState


def test_model_published_event_invalidates_specific_cpf():
    cache = InMemoryHbosBundleCache()
    cache.put(HbosBundle(cpf="111", model_version="v1"))
    cache.put(HbosBundle(cpf="222", model_version="v1"))

    tracker = InstanceModelVersionTracker()
    service = ModelCacheInvalidationService(cache, tracker, instance_id="instance-a")

    event = ModelPublishedEvent(
        model_name="hbos_individual",
        model_version="v2",
        feature_schema_hash="hash-1",
        affected_cpfs=["111"],
    )
    service.handle_model_published(event)

    assert cache.get("111") is None
    assert cache.get("222") is not None


def test_model_published_event_global_invalidation_when_no_cpfs_listed():
    cache = InMemoryHbosBundleCache()
    cache.put(HbosBundle(cpf="111", model_version="v1"))
    cache.put(HbosBundle(cpf="222", model_version="v1"))

    tracker = InstanceModelVersionTracker()
    service = ModelCacheInvalidationService(cache, tracker, instance_id="instance-a")

    event = ModelPublishedEvent(
        model_name="hbos_individual", model_version="v2", feature_schema_hash="hash-1"
    )
    service.handle_model_published(event)

    assert cache.get("111") is None
    assert cache.get("222") is None


def test_instance_tracker_reports_active_version_after_publish():
    cache = InMemoryHbosBundleCache()
    tracker = InstanceModelVersionTracker()
    service = ModelCacheInvalidationService(cache, tracker, instance_id="instance-a")

    event = ModelPublishedEvent(
        model_name="xgboost_global", model_version="xgb-2.0.0", feature_schema_hash="hash-1"
    )
    service.handle_model_published(event)

    assert tracker.stale_instances("xgboost_global", "xgb-2.0.0") == []
    assert tracker.stale_instances("xgboost_global", "xgb-3.0.0") == ["instance-a"]
    assert tracker.convergence_ratio("xgboost_global", "xgb-2.0.0") == 1.0


def test_eager_reload_hook_is_invoked():
    cache = InMemoryHbosBundleCache()
    tracker = InstanceModelVersionTracker()
    reloaded_events = []

    service = ModelCacheInvalidationService(
        cache, tracker, instance_id="instance-a", eager_reload_fn=reloaded_events.append
    )
    event = ModelPublishedEvent(
        model_name="xgboost_global", model_version="xgb-2.0.0", feature_schema_hash="hash-1"
    )
    service.handle_model_published(event)

    assert reloaded_events == [event]


def test_model_registry_register_promote_and_rollback():
    registry = ModelRegistry()
    registry.register("xgboost_global", "1.0.0", feature_schema_hash="hash-1")
    registry.register("xgboost_global", "2.0.0", feature_schema_hash="hash-1")

    registry.promote("xgboost_global", "1.0.0")
    assert registry.active_version("xgboost_global") == "1.0.0"

    registry.promote("xgboost_global", "2.0.0")
    assert registry.active_version("xgboost_global") == "2.0.0"
    assert registry.get("xgboost_global", "1.0.0").state == ModelRegistryState.DEPRECATED

    registry.rollback("xgboost_global")
    assert registry.active_version("xgboost_global") == "1.0.0"
    assert registry.get("xgboost_global", "2.0.0").state == ModelRegistryState.ROLLED_BACK


def test_model_registry_rollback_without_history_raises():
    registry = ModelRegistry()
    registry.register("xgboost_global", "1.0.0", feature_schema_hash="hash-1")
    registry.promote("xgboost_global", "1.0.0")

    with pytest.raises(ModelRegistryError):
        registry.rollback("xgboost_global")


def test_model_registry_promote_unregistered_raises():
    registry = ModelRegistry()
    with pytest.raises(ModelRegistryError):
        registry.promote("xgboost_global", "9.9.9")
