from __future__ import annotations

from antifraud.challenge.context_store import ChallengeContextStore
from antifraud.challenge.events import ChallengeEventPublisher, build_challenge_event
from antifraud.challenge.notifications import NotificationService
from antifraud.challenge.triage_queue import TriageQueue
from antifraud.challenge.workflow import ChallengeWorkflow
from antifraud.domain.enums import Decision
from antifraud.domain.models import ChallengeEvent, DecisionTrace, WorkflowResult


class ChallengeOperationsService:
    """Implementa a sequência de operacionalização do challenge (Evolução prioritária 1).

    Cobre os passos 1-4 e 7 da sequência documentada:
    1. publicação de evento; 2. persistência de contexto/evidências;
    3. fila de triagem; 4. workflow de validadores; 7. notificação.

    Step-up de autenticação (passo 5), fila de análise humana dedicada para
    ``escalate`` (passo 6) e integrações externas (passo 8) são pontos de
    extensão explícitos (hooks) e agentes de IA assíncronos (passo 9) são
    propositalmente NÃO implementados aqui -- eles só devem ser
    introduzidos depois que os controles determinísticos estiverem
    operacionais em produção, conforme a diretriz do contexto operacional.
    """

    def __init__(
        self,
        publisher: ChallengeEventPublisher,
        context_store: ChallengeContextStore,
        triage_queue: TriageQueue,
        workflow: ChallengeWorkflow,
        notification_service: NotificationService,
        escalation_queue: TriageQueue | None = None,
        step_up_hook=None,
    ) -> None:
        self._publisher = publisher
        self._context_store = context_store
        self._triage_queue = triage_queue
        self._workflow = workflow
        self._notification_service = notification_service
        self._escalation_queue = escalation_queue
        self._step_up_hook = step_up_hook

    def handle_challenge_decision(self, trace: DecisionTrace, cpf: str) -> ChallengeEvent:
        """Publica o evento de challenge e persiste o contexto (idempotente).

        Chamado pelo serviço de decisão sempre que a cascata resulta em
        ``challenge``. Não bloqueia o hot path: apenas emite o evento e
        retorna imediatamente.
        """

        event = build_challenge_event(trace, cpf)

        is_new = self._context_store.save_context(event)
        if is_new:
            self._publisher.publish(event)
            self._triage_queue.enqueue(event)

        return event

    def process_next_in_triage(self) -> WorkflowResult | None:
        """Processa o próximo item da fila de triagem através do workflow de validadores."""

        event = self._triage_queue.dequeue()
        if event is None:
            return None
        return self.process_event(event)

    def process_event(self, event: ChallengeEvent) -> WorkflowResult:
        if self._step_up_hook is not None:
            self._step_up_hook(event)

        result = self._workflow.run(event)

        if result.final_decision == Decision.ESCALATE and self._escalation_queue is not None:
            self._escalation_queue.enqueue(event)

        self._notification_service.notify(
            transaction_id=event.transaction_id,
            correlation_id=event.correlation_id,
            decision=result.final_decision,
        )
        return result
