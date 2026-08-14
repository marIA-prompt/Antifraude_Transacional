from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from antifraud.domain.models import TransactionPayload
from antifraud.service import AntifraudService

router = APIRouter(prefix="/v1", tags=["v1"])


class DecisionFinalResponse(BaseModel):
    """Contrato AS-IS observado em produção: apenas ``decision_final``.

    Mantido por retrocompatibilidade. Score, sinais, features e pesos NÃO
    são expostos aqui -- consumidores que precisem de explicabilidade
    devem usar a API v2 (autenticada e autorizada por perfil).
    """

    decision_final: str


@router.post("/transactions/authorize", response_model=DecisionFinalResponse)
def authorize_transaction(payload: TransactionPayload, request: Request) -> DecisionFinalResponse:
    service: AntifraudService = request.app.state.antifraud_service
    result = service.decide(payload)
    return DecisionFinalResponse(decision_final=result.decision.value)
