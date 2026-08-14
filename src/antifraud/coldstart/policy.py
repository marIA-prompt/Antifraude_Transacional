from __future__ import annotations

from dataclasses import dataclass, field

from antifraud.domain.enums import Decision
from antifraud.domain.models import TransactionPayload


@dataclass
class ColdStartThresholds:
    """Thresholds configuráveis por canal/produto (sem redeploy, em tese via config store).

    Os valores default aqui são apenas um ponto de partida ilustrativo; a
    revisão periódica de impacto em atrito/receita/perda por fraude deve
    ajustar estes números por canal, produto e tipo de transação.
    """

    low_value_ceiling: float = 200.0
    high_value_floor: float = 3000.0
    hbos_weight_reduction_factor: float = 0.0
    """0.0 = peso nulo para HBOS em cold start; 1.0 = sem redução."""
    global_model_weight_boost: float = 1.3
    """Multiplicador aplicado ao peso do modelo global (XGBoost) em cold start."""


@dataclass
class ColdStartDecisionHint:
    """Sugestão de decisão e ajuste de pesos para transações de CPF novo."""

    is_cold_start: bool
    suggested_decision: Decision | None
    reason_codes: list[str] = field(default_factory=list)
    hbos_weight_multiplier: float = 1.0
    global_model_weight_multiplier: float = 1.0


class ColdStartPolicy:
    """Política de cold start configurável (Evolução prioritária 3).

    A política não decide sozinha: ela ajusta pesos dos modelos e pode
    sugerir uma decisão inicial (approve com monitoramento, challenge com
    step-up, deny/escalate), que continua sujeita a hard rules e à
    cascata de decisão completa.
    """

    def __init__(self, thresholds: ColdStartThresholds | None = None):
        self._thresholds = thresholds or ColdStartThresholds()

    def evaluate(
        self,
        payload: TransactionPayload,
        is_cold_start: bool,
        has_critical_hard_rule: bool,
    ) -> ColdStartDecisionHint:
        if not is_cold_start:
            return ColdStartDecisionHint(is_cold_start=False, suggested_decision=None)

        t = self._thresholds
        reason_codes = ["cold_start"]

        if has_critical_hard_rule:
            return ColdStartDecisionHint(
                is_cold_start=True,
                suggested_decision=Decision.DENY,
                reason_codes=reason_codes + ["cold_start_hard_rule"],
                hbos_weight_multiplier=t.hbos_weight_reduction_factor,
                global_model_weight_multiplier=t.global_model_weight_boost,
            )

        if payload.amount <= t.low_value_ceiling:
            suggested = Decision.APPROVE
            reason_codes.append("cold_start_low_value_monitored")
        elif payload.amount >= t.high_value_floor:
            suggested = Decision.ESCALATE
            reason_codes.append("cold_start_high_value")
        else:
            suggested = Decision.CHALLENGE
            reason_codes.append("cold_start_intermediate_value_stepup")

        return ColdStartDecisionHint(
            is_cold_start=True,
            suggested_decision=suggested,
            reason_codes=reason_codes,
            hbos_weight_multiplier=t.hbos_weight_reduction_factor,
            global_model_weight_multiplier=t.global_model_weight_boost,
        )
