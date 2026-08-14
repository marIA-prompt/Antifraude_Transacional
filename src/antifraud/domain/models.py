from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from antifraud.domain.enums import (
    Decision,
    Layer,
    ValidatorExecutionStatus,
    ValidatorOutcome,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TransactionPayload(BaseModel):
    """Payload de entrada da transação (AS-IS: validação do payload).

    Campos obrigatórios mínimos para a cascata de decisão. ``cpf`` é mantido
    apenas em memória de processo / eventos internos tokenizados; nunca deve
    ser exposto em resposta HTTP (ver mascaramento na API v2).
    """

    transaction_id: str
    correlation_id: str
    cpf: str = Field(..., description="CPF do titular. Tokenizado antes de sair do processo.")
    amount: float = Field(..., ge=0)
    currency: str = "BRL"
    channel: str = "app"
    product: str = "credit_card"
    installments: int = Field(default=1, ge=1)
    merchant_id: Optional[str] = None
    merchant_is_new: bool = False
    device_id: Optional[str] = None
    geolocation: Optional[dict[str, float]] = None
    timestamp: datetime = Field(default_factory=_utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)


class Signal(BaseModel):
    """Sinal de risco emitido por qualquer camada (modelo ou regra)."""

    name: str
    source: Layer
    value: float | str | bool
    description: str = ""


class RuleEvidence(BaseModel):
    """Evidência auditável de uma regra de negócio ou hard rule acionada."""

    rule_id: str
    reason_code: str
    description: str
    is_hard_rule: bool = False
    triggered: bool = True


class ModelScore(BaseModel):
    model_name: str
    model_version: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class LayerExecutionRecord(BaseModel):
    """Registro de execução de uma camada, para observabilidade do short-circuit."""

    layer: Layer
    executed: bool
    duration_ms: float = 0.0
    outcome: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)


class DecisionTrace(BaseModel):
    """Rastro completo de observabilidade de uma decisão (ver seção Short-circuit).

    Contém tudo que deve ser registrado para toda transação, incluindo
    camadas executadas/não executadas, scores, sinais, regras e versões de
    modelo. É o objeto persistido/auditado internamente e a fonte de dados
    para a API v2 e para o evento ``fraud.challenge.created``.
    """

    transaction_id: str
    correlation_id: str
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
    layer_executions: list[LayerExecutionRecord] = Field(default_factory=list)
    terminating_layer: Optional[Layer] = None
    hbos_score: Optional[ModelScore] = None
    xgboost_score: Optional[ModelScore] = None
    consolidated_score: Optional[float] = None
    signals: list[Signal] = Field(default_factory=list)
    rule_evidences: list[RuleEvidence] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    feature_weights: dict[str, float] = Field(default_factory=dict)
    decision: Optional[Decision] = None
    reason_codes: list[str] = Field(default_factory=list)
    is_cold_start: bool = False
    fallback_reason: Optional[str] = None
    is_shadow_sample: bool = False

    def executed_layers(self) -> list[Layer]:
        return [rec.layer for rec in self.layer_executions if rec.executed]

    def skipped_layers(self) -> list[Layer]:
        return [rec.layer for rec in self.layer_executions if not rec.executed]


class DecisionResult(BaseModel):
    """Resultado consolidado retornado pelo motor de decisão (uso interno)."""

    decision: Decision
    trace: DecisionTrace


class ChallengeEvent(BaseModel):
    """Evento ``fraud.challenge.created`` publicado para transações challenge.

    Campos alinhados à seção "Dados mínimos do evento de challenge" do
    contexto operacional. O orquestrador de challenge consome este evento e
    NÃO depende da resposta HTTP v1.
    """

    event_name: str = "fraud.challenge.created"
    transaction_id: str
    correlation_id: str
    cpf_token: str
    timestamp: datetime = Field(default_factory=_utcnow)
    hbos_score: Optional[float] = None
    xgboost_score: Optional[float] = None
    consolidated_score: Optional[float] = None
    signals: list[Signal] = Field(default_factory=list)
    rule_evidences: list[RuleEvidence] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    model_versions: dict[str, str] = Field(default_factory=dict)
    executed_layers: list[Layer] = Field(default_factory=list)
    terminating_layer: Optional[Layer] = None
    initial_decision: Decision = Decision.CHALLENGE
    context: dict[str, Any] = Field(default_factory=dict)


class ValidatorResult(BaseModel):
    """Resultado de um validador do workflow de challenge.

    Contempla os requisitos: duração, resultado, erro, timeout e fallback.
    """

    validator_name: str
    contract_version: str
    outcome: Optional[ValidatorOutcome] = None
    execution_status: ValidatorExecutionStatus = ValidatorExecutionStatus.OK
    duration_ms: float = 0.0
    reason_codes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    used_fallback: bool = False


class WorkflowResult(BaseModel):
    """Resultado consolidado do workflow de validadores para um challenge."""

    transaction_id: str
    correlation_id: str
    final_decision: Decision
    validator_results: list[ValidatorResult] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    finished_at: datetime = Field(default_factory=_utcnow)
    idempotency_replayed: bool = False


class NotificationRecord(BaseModel):
    transaction_id: str
    correlation_id: str
    decision: Decision
    channel: str = "webhook"
    sent_at: datetime = Field(default_factory=_utcnow)
    idempotency_key: str = ""
    delivered: bool = True
