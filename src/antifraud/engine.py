"""Hot-path decision cascade (TO-BE). AutoML and agents are intentionally absent."""

from __future__ import annotations

import hashlib
from typing import Any

from antifraud.cache import ModelCache
from antifraud.challenge import ChallengeOutbox
from antifraud.models import ALL_LAYERS, Decision, DecisionResult, ModelVersions, Transaction
from antifraud.policy import PolicyConfig


class PayloadValidationError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _stub_score(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class ScoreEngine:
    """Deterministic policy simulator. Not the production microservice."""

    def __init__(
        self,
        policy: PolicyConfig,
        cache: ModelCache | None = None,
        outbox: ChallengeOutbox | None = None,
        shadow_force: bool | None = None,
    ) -> None:
        self.policy = policy
        self.cache = cache or ModelCache()
        self.outbox = outbox or ChallengeOutbox()
        self.shadow_force = shadow_force

    def reload_policy(self, policy: PolicyConfig) -> None:
        self.policy = policy

    def score(self, tx: Transaction) -> DecisionResult:
        self._validate(tx)
        features = self._features(tx)
        executed: list[str] = ["payload", "features"]
        signals: list[str] = []
        reasons: list[str] = []

        versions = ModelVersions(
            hbos=self.cache.active_version("hbos"),
            xgboost=self.cache.active_version("xgboost"),
            policy=self.policy.policy_version,
        )

        hard_decision, hard_signals, hard_reasons = self._hard_rules(tx)
        executed.append("hard_rules")
        signals.extend(hard_signals)
        reasons.extend(hard_reasons)

        result: DecisionResult | None = None
        if hard_decision == "deny":
            result = self._finish(
                tx,
                decision="deny",
                score=1.0,
                score_hbos=None,
                score_xgboost=None,
                signals=signals,
                reasons=reasons,
                features=features,
                executed=executed,
                terminated_by="hard_rules",
                versions=versions,
            )

        if result is None:
            cold = self._cold_start(tx)
            executed.append("cold_start")
            if cold is not None:
                decision, score, extra_signals, extra_reasons = cold
                signals.extend(extra_signals)
                reasons.extend(extra_reasons)
                result = self._finish(
                    tx,
                    decision=decision,
                    score=score,
                    score_hbos=None,
                    score_xgboost=None,
                    signals=signals,
                    reasons=reasons,
                    features=features,
                    executed=executed,
                    terminated_by="cold_start",
                    versions=versions,
                )

        shadow = self._should_shadow(tx)
        need_models = result is None or shadow

        score_hbos: float | None = None
        score_xgb: float | None = None
        if need_models:
            score_hbos = self._hbos(tx)
            score_xgb = self._xgboost(tx, features)
            if result is None:
                executed.extend(["hbos", "xgboost", "consolidation"])
                signals.append("hbos_anomaly" if (score_hbos or 0) >= 0.8 else "hbos_typical")
                if tx.is_new_subject or tx.history_days < self.policy.thin_file_days:
                    reasons.append("cold_start")
                    signals.append("thin_file_or_new_subject")
                decision, consolidated, extra_reasons = self._consolidate(
                    tx, score_hbos, score_xgb
                )
                reasons.extend(extra_reasons)
                result = self._finish(
                    tx,
                    decision=decision,
                    score=consolidated,
                    score_hbos=score_hbos,
                    score_xgboost=score_xgb,
                    signals=signals,
                    reasons=reasons,
                    features=features,
                    executed=executed,
                    terminated_by="consolidation",
                    versions=versions,
                )
            else:
                result.shadow_evaluated = True
                shadow_decision, shadow_score, _ = self._consolidate(
                    tx, score_hbos, score_xgb
                )
                result.shadow_would_decide = shadow_decision
                result.score_hbos = score_hbos
                result.score_xgboost = score_xgb
                result.features = features
                # Shadow must not change the online decision or consolidated score.
                _ = shadow_score

        assert result is not None
        if shadow and not result.shadow_evaluated and result.terminated_by == "consolidation":
            result.shadow_evaluated = True
            result.shadow_would_decide = result.decision

        self.outbox.publish(tx, result)
        return result

    def _should_shadow(self, tx: Transaction) -> bool:
        if self.shadow_force is True:
            return True
        if self.shadow_force is False:
            return False
        digest = hashlib.sha256(tx.transaction_id.encode("utf-8")).digest()
        bucket = digest[0] / 255.0
        return bucket < self.policy.shadow_rate

    def _validate(self, tx: Transaction) -> None:
        if not tx.transaction_id or not tx.correlation_id or not tx.subject_id:
            raise PayloadValidationError("invalid_payload", "missing identifiers")
        if tx.amount < 0:
            raise PayloadValidationError("invalid_amount", "amount must be >= 0")
        if not tx.timestamp:
            raise PayloadValidationError("invalid_timestamp", "timestamp required")
        if tx.subject_id.lower().startswith("cpf:"):
            raise PayloadValidationError("lgpd_cpf_forbidden", "subject_id must be tokenized")

    def _features(self, tx: Transaction) -> dict[str, Any]:
        return {
            "amount": tx.amount,
            "installments": tx.installments,
            "history_days": tx.history_days,
            "is_new_subject": tx.is_new_subject,
            "channel": tx.channel,
            "rule_83_candidate": tx.rule_83_candidate,
            "amount_band": (
                "low"
                if tx.amount <= self.policy.low_value_max
                else "mid"
                if tx.amount <= self.policy.mid_value_max
                else "high"
            ),
        }

    def _hard_rules(self, tx: Transaction) -> tuple[Decision | None, list[str], list[str]]:
        signals: list[str] = []
        reasons: list[str] = []
        if tx.rule_83_candidate:
            signals.append("rule_83_triggered")
            reasons.append("rule_83_triggered")
        else:
            signals.append("rule_83_not_triggered")
        if tx.critical_hard_rule:
            reasons.append("hard_rule_critical")
            signals.append("hard_rule_critical")
            return "deny", signals, reasons
        return None, signals, reasons

    def _cold_start(
        self, tx: Transaction
    ) -> tuple[Decision, float, list[str], list[str]] | None:
        new = tx.is_new_subject or tx.history_days < self.policy.thin_file_days
        if not new:
            return None
        reasons = ["cold_start"]
        signals = ["new_or_thin_file"]
        if tx.amount > self.policy.mid_value_max:
            reasons.append("cold_start_high_value")
            return "deny", 0.99, signals, reasons
        if tx.amount > self.policy.low_value_max:
            reasons.append("cold_start_step_up")
            return "challenge", 0.6, signals, reasons
        reasons.append("cold_start_low_value_monitor")
        return "approve", 0.2, signals, reasons

    def _hbos(self, tx: Transaction) -> float:
        if tx.injected_hbos is not None:
            return _clip(tx.injected_hbos)
        return _clip(_stub_score(f"hbos:{tx.subject_id}:{tx.amount}"))

    def _xgboost(self, tx: Transaction, features: dict[str, Any]) -> float:
        if tx.injected_xgboost is not None:
            return _clip(tx.injected_xgboost)
        bump = 0.15 if tx.rule_83_candidate else 0.0
        return _clip(_stub_score(f"xgb:{tx.transaction_id}") + bump)

    def _consolidate(
        self, tx: Transaction, hbos: float, xgb: float
    ) -> tuple[Decision, float, list[str]]:
        new = tx.is_new_subject or tx.history_days < self.policy.thin_file_days
        hbos_w = self.policy.hbos_new_subject_weight if new else self.policy.hbos_weight
        xgb_w = self.policy.xgboost_weight
        total = hbos_w + xgb_w
        consolidated = _clip((hbos_w * hbos + xgb_w * xgb) / total if total else xgb)
        reasons = ["hbos_weight_reduced" if new else "hbos_weight_full"]
        if consolidated <= self.policy.approve_max:
            return "approve", consolidated, reasons
        if consolidated <= self.policy.challenge_max:
            return "challenge", consolidated, reasons
        hbos_only = hbos >= 0.8 and xgb <= self.policy.approve_max
        if hbos_only:
            reasons.append("hbos_signal_not_fraud_proof")
            return "challenge", consolidated, reasons
        reasons.append("consolidated_high_risk")
        return "deny", consolidated, reasons

    def _finish(
        self,
        tx: Transaction,
        decision: Decision,
        score: float,
        score_hbos: float | None,
        score_xgboost: float | None,
        signals: list[str],
        reasons: list[str],
        features: dict[str, Any],
        executed: list[str],
        terminated_by: str,
        versions: ModelVersions,
    ) -> DecisionResult:
        skipped = [layer for layer in ALL_LAYERS if layer not in executed]
        weights = {
            "hbos": (
                self.policy.hbos_new_subject_weight
                if tx.is_new_subject or tx.history_days < self.policy.thin_file_days
                else self.policy.hbos_weight
            ),
            "xgboost": self.policy.xgboost_weight,
        }
        return DecisionResult(
            decision=decision,
            score=score,
            score_hbos=score_hbos,
            score_xgboost=score_xgboost,
            signals=signals,
            reason_codes=reasons,
            features=features,
            feature_weights=weights,
            layers_executed=executed,
            layers_skipped=skipped,
            terminated_by=terminated_by,
            model_versions=versions,
            correlation_id=tx.correlation_id,
            transaction_id=tx.transaction_id,
            subject_id=tx.subject_id,
        )
