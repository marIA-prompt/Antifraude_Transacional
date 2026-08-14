from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from antifraud.domain.models import DecisionTrace

audit_logger = logging.getLogger("antifraud.audit")


class AuditSink(ABC):
    """Destino de auditoria: banco de auditoria, tópico de mensageria ou logs estruturados.

    O contexto operacional exige que TODA transação registre camadas
    executadas/não executadas, scores, sinais, regras, versões de modelo e
    decisão -- independentemente do que a API HTTP expõe.
    """

    @abstractmethod
    def record(self, trace: DecisionTrace) -> None:
        raise NotImplementedError


class StructuredLoggingAuditSink(AuditSink):
    """Registra o trace completo como uma linha de log estruturado (JSON)."""

    def record(self, trace: DecisionTrace) -> None:
        payload = trace.model_dump(mode="json")
        audit_logger.info(json.dumps(payload, ensure_ascii=False))


class InMemoryAuditSink(AuditSink):
    """Implementação de referência para testes: mantém os traces em memória."""

    def __init__(self) -> None:
        self._traces: list[DecisionTrace] = []

    def record(self, trace: DecisionTrace) -> None:
        self._traces.append(trace)

    @property
    def traces(self) -> list[DecisionTrace]:
        return list(self._traces)

    def find(self, transaction_id: str, correlation_id: str) -> DecisionTrace | None:
        for trace in self._traces:
            if trace.transaction_id == transaction_id and trace.correlation_id == correlation_id:
                return trace
        return None


class CompositeAuditSink(AuditSink):
    def __init__(self, sinks: list[AuditSink]):
        self._sinks = sinks

    def record(self, trace: DecisionTrace) -> None:
        for sink in self._sinks:
            sink.record(trace)
