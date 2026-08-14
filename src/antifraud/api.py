"""HTTP contract shaping. v1 never includes explainability fields."""

from __future__ import annotations

from typing import Iterable

from antifraud.models import DecisionResult

V1_ALLOWED_KEYS = frozenset({"decision_final"})


def to_v1(result: DecisionResult) -> dict:
    return {"decision_final": result.decision}


def to_v2(result: DecisionResult, scopes: Iterable[str] | None = None) -> dict:
    scopes = set(scopes or [])
    if "score:read" not in scopes:
        raise PermissionError("missing scope score:read")
    body = {
        "score": result.score,
        "decision": result.decision,
        "signals": list(result.signals),
        "reason_codes": list(result.reason_codes),
        "correlation_id": result.correlation_id,
        "layers_executed": list(result.layers_executed),
        "layers_skipped": list(result.layers_skipped),
        "terminated_by": result.terminated_by,
        "model_versions": result.model_versions.as_dict(),
        "subject_id": result.subject_id,
    }
    if "explain:features" in scopes:
        body["features"] = dict(result.features)
    if "explain:weights" in scopes:
        body["feature_weights"] = dict(result.feature_weights)
    return body
