from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from antifraud.domain.enums import ModelRegistryState


class ModelRegistryError(Exception):
    pass


@dataclass
class ModelRegistryEntry:
    model_name: str
    model_version: str
    state: ModelRegistryState
    feature_schema_hash: str
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


class ModelRegistry:
    """Registro de versões de modelo (candidate/challenger/champion/deprecated/rolled_back).

    AS-IS/TO-BE: hoje não há model registry formalizado; esta classe é a
    interface mínima proposta para suportar publicação atômica, promoção e
    rollback rápido (Evolução prioritária 2), sem presumir integração real
    com um serviço externo de registry.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], ModelRegistryEntry] = {}
        self._active_version: dict[str, str] = {}
        self._history: dict[str, list[str]] = {}

    def register(
        self,
        model_name: str,
        model_version: str,
        feature_schema_hash: str,
        state: ModelRegistryState = ModelRegistryState.CANDIDATE,
        metadata: dict | None = None,
    ) -> ModelRegistryEntry:
        entry = ModelRegistryEntry(
            model_name=model_name,
            model_version=model_version,
            state=state,
            feature_schema_hash=feature_schema_hash,
            metadata=metadata or {},
        )
        self._entries[(model_name, model_version)] = entry
        return entry

    def promote(self, model_name: str, model_version: str) -> ModelRegistryEntry:
        key = (model_name, model_version)
        entry = self._entries.get(key)
        if entry is None:
            raise ModelRegistryError(f"Modelo não registrado: {model_name}:{model_version}")

        current_champion = self._active_version.get(model_name)
        if current_champion and current_champion != model_version:
            old_key = (model_name, current_champion)
            if old_key in self._entries:
                self._entries[old_key].state = ModelRegistryState.DEPRECATED
            self._history.setdefault(model_name, []).append(current_champion)

        entry.state = ModelRegistryState.CHAMPION
        self._active_version[model_name] = model_version
        return entry

    def rollback(self, model_name: str) -> ModelRegistryEntry:
        history = self._history.get(model_name, [])
        if not history:
            raise ModelRegistryError(f"Sem versão anterior para rollback de {model_name}")

        previous_version = history.pop()
        current = self._active_version.get(model_name)
        if current:
            self._entries[(model_name, current)].state = ModelRegistryState.ROLLED_BACK

        entry = self._entries[(model_name, previous_version)]
        entry.state = ModelRegistryState.CHAMPION
        self._active_version[model_name] = previous_version
        return entry

    def active_version(self, model_name: str) -> str | None:
        return self._active_version.get(model_name)

    def get(self, model_name: str, model_version: str) -> ModelRegistryEntry | None:
        return self._entries.get((model_name, model_version))
