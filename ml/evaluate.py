"""Métricas mínimas de promoção (MLOps) — nenhuma decisão por métrica isolada."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)


def decisions_from_proba(proba: np.ndarray, policy: dict) -> np.ndarray:
    """Mapeia probabilidade calibrada em approve/challenge/deny (ADR-0001)."""
    lower = policy["challenge_band"]["lower"]
    upper = policy["challenge_band"]["upper"]
    out = np.where(proba >= upper, "deny", np.where(proba >= lower, "challenge", "approve"))
    return out


def metric_set(y_true: np.ndarray, proba: np.ndarray, policy: dict) -> dict:
    """Conjunto mínimo obrigatório para promoção."""
    y_true = np.asarray(y_true).astype(int)
    n = len(y_true)
    result: dict = {"n": int(n), "n_fraude": int(y_true.sum()), "fraud_rate": float(y_true.mean()) if n else 0.0}
    if n == 0 or y_true.sum() == 0 or y_true.sum() == n:
        # Métricas de discriminação indefinidas sem ambas as classes.
        result.update({k: None for k in ["pr_auc", "roc_auc", "recall", "precision", "fpr", "fnr", "brier"]})
    else:
        decisions = decisions_from_proba(proba, policy)
        pred_pos = (decisions == "deny").astype(int)  # "deny" = classe positiva operacional
        tp = int(((pred_pos == 1) & (y_true == 1)).sum())
        fp = int(((pred_pos == 1) & (y_true == 0)).sum())
        fn = int(((pred_pos == 0) & (y_true == 1)).sum())
        tn = int(((pred_pos == 0) & (y_true == 0)).sum())
        result.update(
            {
                "pr_auc": float(average_precision_score(y_true, proba)),
                "roc_auc": float(roc_auc_score(y_true, proba)),
                "recall": float(recall_score(y_true, pred_pos, zero_division=0)),
                "precision": float(precision_score(y_true, pred_pos, zero_division=0)),
                "fpr": float(fp / (fp + tn)) if (fp + tn) else 0.0,
                "fnr": float(fn / (fn + tp)) if (fn + tp) else 0.0,
                "brier": float(brier_score_loss(y_true, proba)),
            }
        )
    # Métricas de operação (independem de haver as duas classes).
    decisions = decisions_from_proba(proba, policy)
    result["challenge_rate"] = float((decisions == "challenge").mean()) if n else 0.0
    result["approve_rate"] = float((decisions == "approve").mean()) if n else 0.0
    result["deny_rate"] = float((decisions == "deny").mean()) if n else 0.0
    return result


def per_cohort_metrics(y_true: np.ndarray, proba: np.ndarray, cohorts: np.ndarray, policy: dict) -> dict:
    out = {}
    for cohort in sorted(set(cohorts)):
        mask = cohorts == cohort
        out[cohort] = metric_set(y_true[mask], proba[mask], policy)
    return out
