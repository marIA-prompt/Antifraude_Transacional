from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from antifraud.domain.models import RuleEvidence, TransactionPayload

RuleFn = Callable[[TransactionPayload, dict[str, float]], Optional[RuleEvidence]]


@dataclass
class Rule:
    """Regra determinística com evidência e reason code auditável.

    ``is_hard_rule=True`` marca regras críticas que podem prevalecer sobre
    scores probabilísticos (deny/short-circuit imediato).
    """

    rule_id: str
    reason_code: str
    description: str
    predicate: RuleFn
    is_hard_rule: bool = False

    def evaluate(
        self, payload: TransactionPayload, features: dict[str, float]
    ) -> RuleEvidence | None:
        return self.predicate(payload, features)


class RulesEngine:
    """Motor de regras de negócio e hard rules (AS-IS: passo 5).

    Hard rules são avaliadas primeiro; a primeira hard rule acionada encerra
    a avaliação (short-circuit) e deve resultar em deny imediato. Regras de
    negócio (não-hard) são sempre avaliadas por completo, pois alimentam o
    XGBoost/consolidação e a explicabilidade, sem encerrar antecipadamente
    a cascata.
    """

    def __init__(self, rules: list[Rule] | None = None):
        self._rules = rules or []

    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    @property
    def hard_rules(self) -> list[Rule]:
        return [r for r in self._rules if r.is_hard_rule]

    @property
    def business_rules(self) -> list[Rule]:
        return [r for r in self._rules if not r.is_hard_rule]

    def evaluate_hard_rules(
        self, payload: TransactionPayload, features: dict[str, float]
    ) -> RuleEvidence | None:
        """Retorna a primeira hard rule crítica acionada, ou None."""

        for rule in self.hard_rules:
            evidence = rule.evaluate(payload, features)
            if evidence is not None and evidence.triggered:
                return evidence
        return None

    def evaluate_business_rules(
        self, payload: TransactionPayload, features: dict[str, float]
    ) -> list[RuleEvidence]:
        evidences = []
        for rule in self.business_rules:
            evidence = rule.evaluate(payload, features)
            if evidence is not None and evidence.triggered:
                evidences.append(evidence)
        return evidences


def default_rules_engine() -> RulesEngine:
    """Conjunto de regras de referência descrito no contexto operacional.

    Thresholds fixos aqui apenas para fins ilustrativos/teste; em produção
    devem ser configuráveis sem redeploy (ver Evolução prioritária 3).
    """

    engine = RulesEngine()

    def blocklist_rule(payload: TransactionPayload, features: dict[str, float]):
        if payload.extra.get("blocklisted"):
            return RuleEvidence(
                rule_id="hard_blocklist",
                reason_code="blocklist_match",
                description="CPF, device ou merchant presente em blocklist.",
                is_hard_rule=True,
            )
        return None

    def impossible_travel_rule(payload: TransactionPayload, features: dict[str, float]):
        if payload.extra.get("impossible_travel"):
            return RuleEvidence(
                rule_id="hard_impossible_travel",
                reason_code="impossible_travel",
                description="Viagem impossível detectada entre transações consecutivas.",
                is_hard_rule=True,
            )
        return None

    def high_value_new_merchant_rule(payload: TransactionPayload, features: dict[str, float]):
        if payload.merchant_is_new and payload.amount > 5000:
            return RuleEvidence(
                rule_id="business_high_value_new_merchant",
                reason_code="high_value_new_merchant",
                description="Alto valor em estabelecimento novo para o cliente.",
                is_hard_rule=False,
            )
        return None

    def odd_hour_rule(payload: TransactionPayload, features: dict[str, float]):
        hour = payload.timestamp.hour
        if hour in range(0, 5) and payload.amount > 1000:
            return RuleEvidence(
                rule_id="business_odd_hour_high_value",
                reason_code="odd_hour_high_value",
                description="Transação de alto valor em horário atípico (madrugada).",
                is_hard_rule=False,
            )
        return None

    def installments_rule(payload: TransactionPayload, features: dict[str, float]):
        if payload.installments >= 10:
            return RuleEvidence(
                rule_id="business_high_installments",
                reason_code="high_installments",
                description="Número elevado de parcelas.",
                is_hard_rule=False,
            )
        return None

    for rule_fn, rule_id, reason_code, desc, hard in [
        (blocklist_rule, "hard_blocklist", "blocklist_match", "Blocklist", True),
        (
            impossible_travel_rule,
            "hard_impossible_travel",
            "impossible_travel",
            "Viagem impossível",
            True,
        ),
        (
            high_value_new_merchant_rule,
            "business_high_value_new_merchant",
            "high_value_new_merchant",
            "Alto valor + estabelecimento novo",
            False,
        ),
        (
            odd_hour_rule,
            "business_odd_hour_high_value",
            "odd_hour_high_value",
            "Horário atípico + alto valor",
            False,
        ),
        (
            installments_rule,
            "business_high_installments",
            "high_installments",
            "Parcelamento elevado",
            False,
        ),
    ]:
        engine.add_rule(
            Rule(
                rule_id=rule_id,
                reason_code=reason_code,
                description=desc,
                predicate=rule_fn,
                is_hard_rule=hard,
            )
        )

    return engine
