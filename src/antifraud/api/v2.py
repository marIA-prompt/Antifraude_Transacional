from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from antifraud.api.deps import require_v2_role
from antifraud.domain.enums import ApiConsumerRole
from antifraud.domain.models import RuleEvidence, Signal, TransactionPayload
from antifraud.service import AntifraudService

router = APIRouter(prefix="/v2", tags=["v2"])


class DecisionExplainabilityResponse(BaseModel):
    """Contrato v2: especificação original preservada + campos de explicabilidade adicionais.

    Consumidores com perfil ``basic`` recebem uma versão mascarada (sem
    features/pesos brutos) para reduzir a exposição indevida da lógica
    antifraude; perfis ``analyst``/``admin`` recebem o detalhe completo.
    """

    transaction_id: str
    correlation_id: str
    score: float | None
    decision: str
    signals: list[Signal]
    features: dict[str, float]
    feature_weights: dict[str, float]
    reason_codes: list[str]
    rule_evidences: list[RuleEvidence]
    model_versions: dict[str, str]
    executed_layers: list[str]
    terminating_layer: str | None
    is_cold_start: bool
    is_shadow_sample: bool


def _mask_for_role(payload: dict[str, Any], role: ApiConsumerRole) -> dict[str, Any]:
    if role == ApiConsumerRole.BASIC:
        payload["features"] = {}
        payload["feature_weights"] = {}
        payload["model_versions"] = {}
        payload["rule_evidences"] = []
    return payload


@router.post("/transactions/authorize", response_model=DecisionExplainabilityResponse)
def authorize_transaction_v2(
    payload: TransactionPayload,
    request: Request,
    role: ApiConsumerRole = Depends(require_v2_role),
) -> DecisionExplainabilityResponse:
    service: AntifraudService = request.app.state.antifraud_service
    result = service.decide(payload)
    trace = result.trace

    model_versions: dict[str, str] = {}
    if trace.hbos_score is not None:
        model_versions["hbos_individual"] = trace.hbos_score.model_version
    if trace.xgboost_score is not None:
        model_versions["xgboost_global"] = trace.xgboost_score.model_version

    response_dict: dict[str, Any] = {
        "transaction_id": trace.transaction_id,
        "correlation_id": trace.correlation_id,
        "score": trace.consolidated_score,
        "decision": result.decision.value,
        "signals": trace.signals,
        "features": trace.features,
        "feature_weights": trace.feature_weights,
        "reason_codes": trace.reason_codes,
        "rule_evidences": trace.rule_evidences,
        "model_versions": model_versions,
        "executed_layers": [layer.value for layer in trace.executed_layers()],
        "terminating_layer": trace.terminating_layer.value if trace.terminating_layer else None,
        "is_cold_start": trace.is_cold_start,
        "is_shadow_sample": trace.is_shadow_sample,
    }
    response_dict = _mask_for_role(response_dict, role)
    return DecisionExplainabilityResponse(**response_dict)
