from __future__ import annotations

import concurrent.futures

from fastapi import FastAPI

from antifraud.api import v1, v2
from antifraud.audit.logger import InMemoryAuditSink
from antifraud.challenge.context_store import InMemoryChallengeContextStore
from antifraud.challenge.events import InMemoryChallengeEventPublisher
from antifraud.challenge.notifications import InMemoryNotificationSender, NotificationService
from antifraud.challenge.service import ChallengeOperationsService
from antifraud.challenge.triage_queue import InMemoryTriageQueue
from antifraud.challenge.validators import (
    AdditionalRulesValidator,
    BlocklistBureauValidator,
    ExtendedHistoryValidator,
    GeoDeviceValidator,
)
from antifraud.challenge.workflow import ChallengeWorkflow, ValidatorStep
from antifraud.coldstart.policy import ColdStartPolicy
from antifraud.decision.cascade import DecisionCascade
from antifraud.features.engine import FeatureEngine
from antifraud.features.profile import InMemoryCustomerProfileRepository
from antifraud.models_ml.hbos import HbosScorer, InMemoryHbosBundleCache
from antifraud.models_ml.xgboost_model import StubXgboostScorer
from antifraud.rules.engine import default_rules_engine
from antifraud.service import AntifraudService


def build_default_antifraud_service() -> AntifraudService:
    """Monta um ``AntifraudService`` com implementações em memória.

    Uso: desenvolvimento local, testes e demonstração da API. Implantações
    reais devem substituir os componentes em memória por integrações
    reais (mensageria, banco de auditoria, cache distribuído etc.),
    respeitando as mesmas interfaces definidas em cada módulo.
    """

    cascade = DecisionCascade(
        rules_engine=default_rules_engine(),
        hbos_scorer=HbosScorer(InMemoryHbosBundleCache()),
        xgboost_scorer=StubXgboostScorer(),
        feature_engine=FeatureEngine(),
        profile_repository=InMemoryCustomerProfileRepository(),
        cold_start_policy=ColdStartPolicy(),
    )

    context_store = InMemoryChallengeContextStore()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    workflow = ChallengeWorkflow(
        steps=[
            ValidatorStep(AdditionalRulesValidator()),
            ValidatorStep(BlocklistBureauValidator()),
            ValidatorStep(GeoDeviceValidator()),
            ValidatorStep(ExtendedHistoryValidator()),
        ],
        context_store=context_store,
        executor=executor,
    )
    challenge_service = ChallengeOperationsService(
        publisher=InMemoryChallengeEventPublisher(),
        context_store=context_store,
        triage_queue=InMemoryTriageQueue(),
        workflow=workflow,
        notification_service=NotificationService(InMemoryNotificationSender()),
    )

    audit_sink = InMemoryAuditSink()

    return AntifraudService(
        cascade=cascade, audit_sink=audit_sink, challenge_service=challenge_service
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Motor de Score Antifraude",
        description=(
            "API v1 (decision_final, retrocompatível) e API v2 "
            "(explicabilidade, autenticada e autorizada por perfil)."
        ),
        version="0.1.0",
    )
    app.state.antifraud_service = build_default_antifraud_service()
    app.include_router(v1.router)
    app.include_router(v2.router)
    return app


app = create_app()
