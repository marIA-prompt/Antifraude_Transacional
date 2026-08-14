from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from antifraud.models_ml.hbos import HbosBundleCache


@dataclass
class ModelPublishedEvent:
    """Evento ``model.published`` (Evolução prioritária 2).

    Emitido pelo pipeline de treino após validar o artefato, registrar a
    versão no model registry e publicar o bundle de forma atômica.
    """

    model_name: str
    model_version: str
    feature_schema_hash: str
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    affected_cpfs: list[str] | None = None
    """Quando ``None``, a invalidação deve ser tratada como global (ex.: XGBoost).
    Quando uma lista, apenas os CPFs afetados devem ser invalidados (ex.: HBOS
    retreinado para um subconjunto de clientes)."""


class InstanceModelVersionTracker:
    """Registra ``model_version_active`` por instância, para detectar defasagem.

    Cada instância do serviço reporta periodicamente qual versão está
    ativa; o dashboard de convergência (fora de escopo deste repositório)
    consome este estado para alertar instâncias desatualizadas.
    """

    def __init__(self) -> None:
        self._active_by_instance: dict[str, dict[str, str]] = {}

    def report(self, instance_id: str, model_name: str, model_version: str) -> None:
        self._active_by_instance.setdefault(instance_id, {})[model_name] = model_version

    def stale_instances(self, model_name: str, expected_version: str) -> list[str]:
        stale = []
        for instance_id, versions in self._active_by_instance.items():
            if versions.get(model_name) != expected_version:
                stale.append(instance_id)
        return stale

    def convergence_ratio(self, model_name: str, expected_version: str) -> float:
        total = len(self._active_by_instance)
        if total == 0:
            return 1.0
        matching = sum(
            1
            for versions in self._active_by_instance.values()
            if versions.get(model_name) == expected_version
        )
        return matching / total


class ModelCacheInvalidationService:
    """Consumidor de ``model.published`` que invalida caches locais/distribuídos.

    Suporta reload lazy (invalida e recarrega sob demanda, no próximo
    ``get``) ou eager (recarrega imediatamente via ``reload_fn``), conforme
    o TO-BE descrito no contexto operacional.
    """

    def __init__(
        self,
        hbos_cache: HbosBundleCache,
        instance_tracker: InstanceModelVersionTracker,
        instance_id: str,
        eager_reload_fn: Callable[[ModelPublishedEvent], None] | None = None,
    ) -> None:
        self._hbos_cache = hbos_cache
        self._instance_tracker = instance_tracker
        self._instance_id = instance_id
        self._eager_reload_fn = eager_reload_fn
        self._applied_events: list[ModelPublishedEvent] = []

    def handle_model_published(self, event: ModelPublishedEvent) -> None:
        if event.model_name == "hbos_individual":
            if event.affected_cpfs is None:
                self._hbos_cache.invalidate()
            else:
                for cpf in event.affected_cpfs:
                    self._hbos_cache.invalidate(cpf)

        if self._eager_reload_fn is not None:
            self._eager_reload_fn(event)

        self._instance_tracker.report(self._instance_id, event.model_name, event.model_version)
        self._applied_events.append(event)

    @property
    def applied_events(self) -> list[ModelPublishedEvent]:
        return list(self._applied_events)
