from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque

from antifraud.domain.models import ChallengeEvent


class TriageQueue(ABC):
    """Fila de triagem (passo 3 da sequência de operacionalização do challenge).

    Desacopla a publicação do evento de challenge do processamento pelo
    workflow de validadores, permitindo controle de vazão, retry e
    priorização.
    """

    @abstractmethod
    def enqueue(self, event: ChallengeEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def dequeue(self) -> ChallengeEvent | None:
        raise NotImplementedError

    @abstractmethod
    def __len__(self) -> int:
        raise NotImplementedError


class InMemoryTriageQueue(TriageQueue):
    def __init__(self) -> None:
        self._queue: deque[ChallengeEvent] = deque()

    def enqueue(self, event: ChallengeEvent) -> None:
        self._queue.append(event)

    def dequeue(self) -> ChallengeEvent | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def __len__(self) -> int:
        return len(self._queue)
