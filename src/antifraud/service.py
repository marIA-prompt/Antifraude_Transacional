from __future__ import annotations

from antifraud.audit.logger import AuditSink
from antifraud.challenge.service import ChallengeOperationsService
from antifraud.decision.cascade import DecisionCascade
from antifraud.domain.enums import Decision
from antifraud.domain.models import DecisionResult, TransactionPayload


class AntifraudService:
    """Fachada que une o fluxo AS-IS de decisão com a operacionalização do challenge.

    Fluxo: cascata de decisão -> auditoria (sempre) -> se ``challenge``,
    aciona a publicação do evento ``fraud.challenge.created`` e a
    persistência de contexto de forma assíncrona/não bloqueante para o
    hot path (a fila de triagem é processada por um worker separado, ver
    ``ChallengeOperationsService.process_next_in_triage``).
    """

    def __init__(
        self,
        cascade: DecisionCascade,
        audit_sink: AuditSink,
        challenge_service: ChallengeOperationsService,
    ) -> None:
        self._cascade = cascade
        self._audit_sink = audit_sink
        self._challenge_service = challenge_service

    def decide(self, payload: TransactionPayload) -> DecisionResult:
        result = self._cascade.decide(payload)
        self._audit_sink.record(result.trace)

        if result.decision == Decision.CHALLENGE:
            self._challenge_service.handle_challenge_decision(result.trace, payload.cpf)

        return result
