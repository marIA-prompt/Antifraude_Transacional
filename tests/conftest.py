from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from antifraud.coldstart.policy import ColdStartPolicy
from antifraud.decision.cascade import DecisionCascade
from antifraud.decision.observability import ShadowSampler
from antifraud.domain.models import TransactionPayload
from antifraud.features.engine import FeatureEngine
from antifraud.features.profile import CustomerProfile, InMemoryCustomerProfileRepository
from antifraud.models_ml.hbos import HbosBundle, HbosScorer, InMemoryHbosBundleCache
from antifraud.models_ml.xgboost_model import StubXgboostScorer
from antifraud.rules.engine import default_rules_engine


def make_payload(**overrides) -> TransactionPayload:
    defaults = dict(
        transaction_id="tx-1",
        correlation_id="corr-1",
        cpf="12345678900",
        amount=100.0,
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return TransactionPayload(**defaults)


@pytest.fixture
def profile_repository() -> InMemoryCustomerProfileRepository:
    repo = InMemoryCustomerProfileRepository()
    repo.upsert(
        CustomerProfile(
            cpf="12345678900",
            first_seen_at=datetime.now(timezone.utc) - timedelta(days=400),
            transaction_count=50,
            history_days=400,
            average_amount=150.0,
        )
    )
    return repo


@pytest.fixture
def hbos_cache() -> InMemoryHbosBundleCache:
    cache = InMemoryHbosBundleCache()
    cache.put(
        HbosBundle(
            cpf="12345678900",
            model_version="hbos-v1",
            feature_means={"amount": 150.0, "amount_to_avg_ratio": 1.0},
            feature_stds={"amount": 50.0, "amount_to_avg_ratio": 0.3},
        )
    )
    return cache


@pytest.fixture
def cascade(profile_repository, hbos_cache) -> DecisionCascade:
    return DecisionCascade(
        rules_engine=default_rules_engine(),
        hbos_scorer=HbosScorer(hbos_cache),
        xgboost_scorer=StubXgboostScorer(),
        feature_engine=FeatureEngine(),
        profile_repository=profile_repository,
        cold_start_policy=ColdStartPolicy(),
        shadow_sampler=ShadowSampler(sample_rate=0.0),
    )
