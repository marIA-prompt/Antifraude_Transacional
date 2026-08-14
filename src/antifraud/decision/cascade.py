from __future__ import annotations

import time
from dataclasses import dataclass

from antifraud.coldstart.policy import ColdStartPolicy
from antifraud.decision.observability import ShadowSampler
from antifraud.domain.enums import Decision, Layer
from antifraud.domain.models import (
    DecisionResult,
    DecisionTrace,
    LayerExecutionRecord,
    Signal,
    TransactionPayload,
)
from antifraud.features.engine import FeatureEngine
from antifraud.features.profile import CustomerProfileRepository, new_customer_profile
from antifraud.models_ml.hbos import HbosScorer
from antifraud.models_ml.xgboost_model import XgboostScorer
from antifraud.rules.engine import RulesEngine
from antifraud.validation.payload import PayloadValidationError, validate_payload


@dataclass
class DecisionThresholds:
    """Bandas de risco configuráveis (consolidação do score global).

    Faixa intermediária => challenge. Estes valores devem ser configuráveis
    sem redeploy em produção (config store / feature flags), mantidos aqui
    como constantes apenas para simplicidade do stub.
    """

    approve_max: float = 0.35
    deny_min: float = 0.75


class DecisionCascade:
    """Orquestra o fluxo AS-IS de decisão em cascata com short-circuit.

    Ordem: validação -> features -> HBOS individual -> hard rules -> regras
    de negócio -> política de cold start -> XGBoost global -> consolidação.

    Toda a execução (camadas executadas/não executadas, scores, sinais,
    regras, versões de modelo, motivo de fallback) é registrada em um
    ``DecisionTrace`` para observabilidade total, mitigando o viés de
    seleção introduzido pelo short-circuit (ver seção "Short-circuit,
    observabilidade e shadow").
    """

    def __init__(
        self,
        rules_engine: RulesEngine,
        hbos_scorer: HbosScorer,
        xgboost_scorer: XgboostScorer,
        feature_engine: FeatureEngine,
        profile_repository: CustomerProfileRepository,
        cold_start_policy: ColdStartPolicy,
        thresholds: DecisionThresholds | None = None,
        shadow_sampler: ShadowSampler | None = None,
    ) -> None:
        self._rules_engine = rules_engine
        self._hbos_scorer = hbos_scorer
        self._xgboost_scorer = xgboost_scorer
        self._feature_engine = feature_engine
        self._profile_repository = profile_repository
        self._cold_start_policy = cold_start_policy
        self._thresholds = thresholds or DecisionThresholds()
        self._shadow_sampler = shadow_sampler or ShadowSampler(sample_rate=0.02)

    def decide(self, payload: TransactionPayload) -> DecisionResult:
        trace = DecisionTrace(
            transaction_id=payload.transaction_id,
            correlation_id=payload.correlation_id,
            is_shadow_sample=self._shadow_sampler.should_sample(),
        )

        start = time.perf_counter()
        try:
            validate_payload(payload)
        except PayloadValidationError as exc:
            trace.layer_executions.append(
                LayerExecutionRecord(
                    layer=Layer.PAYLOAD_VALIDATION,
                    executed=True,
                    duration_ms=_elapsed_ms(start),
                    outcome="rejected",
                    detail={"reason_code": exc.reason_code, "message": exc.message},
                )
            )
            trace.decision = Decision.REJECT
            trace.reason_codes.append(exc.reason_code)
            self._mark_remaining_skipped(trace, after=Layer.PAYLOAD_VALIDATION)
            trace.terminating_layer = Layer.PAYLOAD_VALIDATION
            trace.finished_at = _now()
            return DecisionResult(decision=Decision.REJECT, trace=trace)

        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.PAYLOAD_VALIDATION,
                executed=True,
                duration_ms=_elapsed_ms(start),
                outcome="valid",
            )
        )

        profile = self._profile_repository.get_profile(payload.cpf) or new_customer_profile(
            payload.cpf
        )
        is_cold_start = profile.is_cold_start()
        trace.is_cold_start = is_cold_start

        t0 = time.perf_counter()
        features = self._feature_engine.compute(payload, profile)
        trace.features = features
        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.FEATURE_ENGINEERING, executed=True, duration_ms=_elapsed_ms(t0)
            )
        )

        t0 = time.perf_counter()
        hbos_result = self._hbos_scorer.score(payload.cpf, features)
        hbos_weight_multiplier = 1.0
        if hbos_result is not None:
            trace.hbos_score = hbos_result
            trace.signals.append(
                Signal(
                    name="hbos_score",
                    source=Layer.HBOS_INDIVIDUAL,
                    value=hbos_result.score,
                    description="Score de anomalia comportamental (não é prova de fraude).",
                )
            )
        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.HBOS_INDIVIDUAL,
                executed=True,
                duration_ms=_elapsed_ms(t0),
                outcome="scored" if hbos_result else "no_bundle_cold_start",
            )
        )

        t0 = time.perf_counter()
        hard_rule_evidence = self._rules_engine.evaluate_hard_rules(payload, features)
        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.HARD_RULES,
                executed=True,
                duration_ms=_elapsed_ms(t0),
                outcome="triggered" if hard_rule_evidence else "clear",
            )
        )
        if hard_rule_evidence is not None:
            trace.rule_evidences.append(hard_rule_evidence)
            trace.reason_codes.append(hard_rule_evidence.reason_code)
            trace.decision = Decision.DENY
            trace.terminating_layer = Layer.HARD_RULES
            self._mark_remaining_skipped(trace, after=Layer.HARD_RULES)
            trace.finished_at = _now()
            return DecisionResult(decision=Decision.DENY, trace=trace)

        t0 = time.perf_counter()
        business_evidences = self._rules_engine.evaluate_business_rules(payload, features)
        trace.rule_evidences.extend(business_evidences)
        trace.reason_codes.extend(e.reason_code for e in business_evidences)
        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.BUSINESS_RULES,
                executed=True,
                duration_ms=_elapsed_ms(t0),
                outcome=f"{len(business_evidences)}_triggered",
            )
        )

        t0 = time.perf_counter()
        cold_start_hint = self._cold_start_policy.evaluate(
            payload, is_cold_start=is_cold_start, has_critical_hard_rule=False
        )
        global_weight_multiplier = 1.0
        if cold_start_hint.is_cold_start:
            hbos_weight_multiplier = cold_start_hint.hbos_weight_multiplier
            global_weight_multiplier = cold_start_hint.global_model_weight_multiplier
            trace.reason_codes.extend(cold_start_hint.reason_codes)
        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.COLD_START_POLICY,
                executed=True,
                duration_ms=_elapsed_ms(t0),
                outcome="applied" if cold_start_hint.is_cold_start else "not_applicable",
            )
        )

        t0 = time.perf_counter()
        xgboost_result = self._xgboost_scorer.score(features)
        trace.xgboost_score = xgboost_result
        trace.signals.append(
            Signal(
                name="xgboost_score",
                source=Layer.XGBOOST_GLOBAL,
                value=xgboost_result.score,
                description="Score supervisionado global.",
            )
        )
        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.XGBOOST_GLOBAL, executed=True, duration_ms=_elapsed_ms(t0)
            )
        )

        t0 = time.perf_counter()
        consolidated_score, feature_weights = self._consolidate(
            hbos_score=hbos_result.score if hbos_result else None,
            hbos_weight_multiplier=hbos_weight_multiplier,
            xgboost_score=xgboost_result.score,
            global_weight_multiplier=global_weight_multiplier,
            business_evidence_count=len(business_evidences),
        )
        trace.consolidated_score = consolidated_score
        trace.feature_weights = feature_weights

        if cold_start_hint.is_cold_start and cold_start_hint.suggested_decision is not None:
            decision = cold_start_hint.suggested_decision
        else:
            decision = self._map_score_to_decision(consolidated_score)

        trace.decision = decision
        trace.terminating_layer = Layer.CONSOLIDATION
        trace.layer_executions.append(
            LayerExecutionRecord(
                layer=Layer.CONSOLIDATION,
                executed=True,
                duration_ms=_elapsed_ms(t0),
                outcome=decision.value,
                detail={"consolidated_score": consolidated_score},
            )
        )
        trace.finished_at = _now()

        return DecisionResult(decision=decision, trace=trace)

    def _consolidate(
        self,
        hbos_score: float | None,
        hbos_weight_multiplier: float,
        xgboost_score: float,
        global_weight_multiplier: float,
        business_evidence_count: int,
    ) -> tuple[float, dict[str, float]]:
        base_hbos_weight = 0.35 * hbos_weight_multiplier
        base_xgb_weight = min(0.65 * global_weight_multiplier, 1.0)
        rule_bump = min(business_evidence_count * 0.08, 0.3)

        weights = {"hbos_individual": 0.0, "xgboost_global": base_xgb_weight, "rules_bump": rule_bump}
        weighted_sum = base_xgb_weight * xgboost_score + rule_bump

        if hbos_score is not None and base_hbos_weight > 0:
            weights["hbos_individual"] = base_hbos_weight
            weighted_sum += base_hbos_weight * hbos_score

        total_weight = base_xgb_weight + weights["hbos_individual"]
        normalized = weighted_sum / total_weight if total_weight > 0 else weighted_sum
        consolidated = max(0.0, min(1.0, normalized))
        return round(consolidated, 6), weights

    def _map_score_to_decision(self, score: float) -> Decision:
        if score <= self._thresholds.approve_max:
            return Decision.APPROVE
        if score >= self._thresholds.deny_min:
            return Decision.DENY
        return Decision.CHALLENGE

    @staticmethod
    def _mark_remaining_skipped(trace: DecisionTrace, after: Layer) -> None:
        all_layers = list(Layer)
        idx = all_layers.index(after)
        already_recorded = {rec.layer for rec in trace.layer_executions}
        for layer in all_layers[idx + 1 :]:
            if layer in already_recorded:
                continue
            trace.layer_executions.append(
                LayerExecutionRecord(layer=layer, executed=False, outcome="skipped_short_circuit")
            )


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 4)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
