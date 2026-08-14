"""Domain types for the TO-BE antifraud policy simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["approve", "challenge", "deny"]
Layer = Literal[
    "payload",
    "features",
    "hard_rules",
    "cold_start",
    "hbos",
    "xgboost",
    "consolidation",
]

ALL_LAYERS: tuple[Layer, ...] = (
    "payload",
    "features",
    "hard_rules",
    "cold_start",
    "hbos",
    "xgboost",
    "consolidation",
)


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    correlation_id: str
    subject_id: str
    amount: float
    timestamp: str
    channel: str = "ecommerce"
    product: str = "private_label"
    installments: int = 1
    merchant_id: str = ""
    mcc: str = ""
    device_id: str = ""
    geo_region: str = ""
    rule_83_candidate: bool = False
    history_days: int = 0
    is_new_subject: bool = False
    critical_hard_rule: bool = False
    injected_hbos: float | None = None
    injected_xgboost: float | None = None


@dataclass
class ModelVersions:
    hbos: str
    xgboost: str
    policy: str

    def as_dict(self) -> dict[str, str]:
        return {"hbos": self.hbos, "xgboost": self.xgboost, "policy": self.policy}


@dataclass
class DecisionResult:
    decision: Decision
    score: float
    score_hbos: float | None
    score_xgboost: float | None
    signals: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    feature_weights: dict[str, float] = field(default_factory=dict)
    layers_executed: list[str] = field(default_factory=list)
    layers_skipped: list[str] = field(default_factory=list)
    terminated_by: str = "consolidation"
    model_versions: ModelVersions = field(
        default_factory=lambda: ModelVersions("none", "none", "none")
    )
    fallback_reason: str | None = None
    shadow_evaluated: bool = False
    shadow_would_decide: Decision | None = None
    correlation_id: str = ""
    transaction_id: str = ""
    subject_id: str = ""
