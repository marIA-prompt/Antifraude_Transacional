from __future__ import annotations

from abc import ABC, abstractmethod

from antifraud.domain.enums import Decision
from antifraud.domain.models import NotificationRecord


class NotificationSender(ABC):
    @abstractmethod
    def send(self, record: NotificationRecord) -> None:
        raise NotImplementedError


class InMemoryNotificationSender(NotificationSender):
    def __init__(self) -> None:
        self._sent: list[NotificationRecord] = []

    def send(self, record: NotificationRecord) -> None:
        self._sent.append(record)

    @property
    def sent(self) -> list[NotificationRecord]:
        return list(self._sent)


class NotificationService:
    """Notificação idempotente e rastreável (passo 7 da sequência de challenge).

    Idempotência garantida por ``transaction_id``:``correlation_id``:``decision``:
    reenvios do mesmo desfecho não geram duplicidade observável para o
    consumidor externo.
    """

    def __init__(self, sender: NotificationSender):
        self._sender = sender
        self._sent_keys: set[str] = set()

    def notify(
        self, transaction_id: str, correlation_id: str, decision: Decision, channel: str = "webhook"
    ) -> NotificationRecord:
        key = f"{transaction_id}:{correlation_id}:{decision.value}"
        record = NotificationRecord(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
            decision=decision,
            channel=channel,
            idempotency_key=key,
            delivered=key not in self._sent_keys,
        )
        if key not in self._sent_keys:
            self._sender.send(record)
            self._sent_keys.add(key)
        return record
