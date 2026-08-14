from __future__ import annotations

from abc import ABC, abstractmethod

from antifraud.domain.models import ChallengeEvent


def idempotency_key(transaction_id: str, correlation_id: str) -> str:
    return f"{transaction_id}:{correlation_id}"


class ChallengeContextStore(ABC):
    """Persistência de contexto e evidências da decisão inicial (passo 2 da sequência).

    A chave de idempotência é ``transaction_id`` + ``correlation_id``: o
    fluxo de challenge deve poder ser reprocessado (retry de mensageria,
    reentrega, reinício de instância) sem duplicar efeitos colaterais.
    """

    @abstractmethod
    def save_context(self, event: ChallengeEvent) -> bool:
        """Retorna True se o contexto foi persistido agora, False se já existia (idempotente)."""

        raise NotImplementedError

    @abstractmethod
    def get_context(self, transaction_id: str, correlation_id: str) -> ChallengeEvent | None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, transaction_id: str, correlation_id: str) -> bool:
        raise NotImplementedError


class InMemoryChallengeContextStore(ChallengeContextStore):
    def __init__(self) -> None:
        self._store: dict[str, ChallengeEvent] = {}

    def save_context(self, event: ChallengeEvent) -> bool:
        key = idempotency_key(event.transaction_id, event.correlation_id)
        if key in self._store:
            return False
        self._store[key] = event
        return True

    def get_context(self, transaction_id: str, correlation_id: str) -> ChallengeEvent | None:
        return self._store.get(idempotency_key(transaction_id, correlation_id))

    def exists(self, transaction_id: str, correlation_id: str) -> bool:
        return idempotency_key(transaction_id, correlation_id) in self._store
