from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from antifraud.domain.enums import Decision
from antifraud.domain.models import ChallengeEvent, DecisionTrace


def tokenize_cpf(cpf: str) -> str:
    """Tokenização determinística e irreversível do CPF para uso em eventos internos.

    Placeholder para um serviço de tokenização real (vault/HSM). Nunca
    propagar o CPF em claro além da fronteira de validação do payload.
    """

    digest = hashlib.sha256(cpf.encode("utf-8")).hexdigest()
    return f"cpf_tok_{digest[:24]}"


def build_challenge_event(trace: DecisionTrace, cpf: str) -> ChallengeEvent:
    """Monta o evento ``fraud.challenge.created`` a partir do trace de decisão.

    Inclui todos os "Dados mínimos do evento de challenge" definidos no
    contexto operacional: scores, sinais, regras, features, versões de
    modelo, camadas executadas e camada que elevou/encerrou o risco.
    """

    model_versions: dict[str, str] = {}
    if trace.hbos_score is not None:
        model_versions["hbos_individual"] = trace.hbos_score.model_version
    if trace.xgboost_score is not None:
        model_versions["xgboost_global"] = trace.xgboost_score.model_version

    return ChallengeEvent(
        transaction_id=trace.transaction_id,
        correlation_id=trace.correlation_id,
        cpf_token=tokenize_cpf(cpf),
        hbos_score=trace.hbos_score.score if trace.hbos_score else None,
        xgboost_score=trace.xgboost_score.score if trace.xgboost_score else None,
        consolidated_score=trace.consolidated_score,
        signals=trace.signals,
        rule_evidences=trace.rule_evidences,
        features=trace.features,
        model_versions=model_versions,
        executed_layers=trace.executed_layers(),
        terminating_layer=trace.terminating_layer,
        initial_decision=trace.decision or Decision.CHALLENGE,
        context={
            "is_cold_start": trace.is_cold_start,
            "reason_codes": trace.reason_codes,
        },
    )


class ChallengeEventPublisher(ABC):
    """Publica ``fraud.challenge.created`` de forma assíncrona (não bloqueia o hot path).

    Implementações de produção usariam um tópico de mensageria (Kafka,
    SNS/SQS, Service Bus etc.). Esta interface mantém o motor de decisão
    desacoplado do transporte.
    """

    @abstractmethod
    def publish(self, event: ChallengeEvent) -> None:
        raise NotImplementedError


class InMemoryChallengeEventPublisher(ChallengeEventPublisher):
    """Implementação de referência para testes e desenvolvimento local."""

    def __init__(self) -> None:
        self._published: list[ChallengeEvent] = []

    def publish(self, event: ChallengeEvent) -> None:
        self._published.append(event)

    @property
    def published_events(self) -> list[ChallengeEvent]:
        return list(self._published)
