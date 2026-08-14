from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from antifraud.domain.enums import ValidatorOutcome
from antifraud.domain.models import ChallengeEvent


@dataclass
class ValidatorOutput:
    """Saída funcional de um validador, antes de ser envolvida pelo wrapper de resiliência."""

    outcome: ValidatorOutcome
    reason_codes: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    high_confidence: bool = False
    """Quando True e outcome == DENY, o workflow pode encerrar antecipadamente."""


class ChallengeValidator(ABC):
    """Contrato versionado de um validador do workflow de challenge.

    Cada validador deve ser testável isoladamente e não deve bloquear
    indefinidamente uma decisão -- por isso ``validate`` deve ser uma
    chamada síncrona e rápida (o controle de timeout real é aplicado pelo
    orquestrador do workflow, ver ``workflow.py``).
    """

    name: str
    contract_version: str = "v1"

    @abstractmethod
    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        raise NotImplementedError


class AdditionalRulesValidator(ChallengeValidator):
    """Regras adicionais e calibração de decisão (passo 4 da sequência)."""

    name = "additional_rules_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        reason_codes = [r.reason_code for r in event.rule_evidences]
        if event.consolidated_score is not None and event.consolidated_score >= 0.9:
            return ValidatorOutput(
                outcome=ValidatorOutcome.DENY,
                reason_codes=reason_codes + ["calibrated_high_risk"],
                evidence={"consolidated_score": event.consolidated_score},
                high_confidence=True,
            )
        return ValidatorOutput(
            outcome=ValidatorOutcome.ESCALATE,
            reason_codes=reason_codes,
            evidence={"consolidated_score": event.consolidated_score},
        )


class BlocklistBureauValidator(ChallengeValidator):
    """Integração com blocklist/bureau externos (passo 8 da sequência).

    Implementação de referência: consulta um blocklist local injetado via
    ``event.context``. A integração real com bureau externo é um ponto de
    extensão (fora de escopo deste repositório).
    """

    name = "blocklist_bureau_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        bureau_flag = event.context.get("bureau_negative_record", False)
        if bureau_flag:
            return ValidatorOutput(
                outcome=ValidatorOutcome.DENY,
                reason_codes=["bureau_negative_record"],
                evidence={"bureau_negative_record": True},
                high_confidence=True,
            )
        return ValidatorOutput(outcome=ValidatorOutcome.ESCALATE, reason_codes=[])


class GeoDeviceValidator(ChallengeValidator):
    """Validação de geolocalização e device intelligence."""

    name = "geo_device_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        suspicious_device = event.context.get("suspicious_device", False)
        if suspicious_device:
            return ValidatorOutput(
                outcome=ValidatorOutcome.ESCALATE,
                reason_codes=["suspicious_device"],
                evidence={"suspicious_device": True},
            )
        return ValidatorOutput(outcome=ValidatorOutcome.APPROVE, reason_codes=[])


class ExtendedHistoryValidator(ChallengeValidator):
    """Validação de histórico estendido (janela maior que a usada no hot path)."""

    name = "extended_history_validator"

    def validate(self, event: ChallengeEvent) -> ValidatorOutput:
        is_cold_start = event.context.get("is_cold_start", False)
        if is_cold_start:
            return ValidatorOutput(
                outcome=ValidatorOutcome.ESCALATE,
                reason_codes=["cold_start_extended_review"],
                evidence={"is_cold_start": True},
            )
        return ValidatorOutput(outcome=ValidatorOutcome.APPROVE, reason_codes=[])
