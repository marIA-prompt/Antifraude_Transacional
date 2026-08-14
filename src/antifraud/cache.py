"""In-memory double-buffer model registry/cache (TO-BE publication semantics)."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class Artifact:
    name: str
    version: str
    feature_schema_version: str
    payload: bytes
    state: str = "champion"

    @property
    def artifact_hash(self) -> str:
        return sha256(self.payload).hexdigest()


class IncompatibleFeatureSchema(ValueError):
    pass


class ModelCache:
    """Pointer swap without process restart. Not a production serving stack."""

    SUPPORTED_SCHEMA = "features-v1"

    def __init__(self) -> None:
        self._active: dict[str, Artifact] = {
            "hbos": Artifact("hbos", "hbos-unspecified", self.SUPPORTED_SCHEMA, b"hbos-0"),
            "xgboost": Artifact(
                "xgboost", "xgb-unspecified", self.SUPPORTED_SCHEMA, b"xgb-0"
            ),
        }
        self._previous: dict[str, Artifact] = {}
        self.stale_instances: list[str] = []

    def active_version(self, name: str) -> str:
        return self._active[name].version

    def publish(self, artifact: Artifact) -> Artifact:
        if artifact.feature_schema_version != self.SUPPORTED_SCHEMA:
            raise IncompatibleFeatureSchema(
                f"{artifact.feature_schema_version} != {self.SUPPORTED_SCHEMA}"
            )
        if artifact.state not in {"challenger", "champion"}:
            raise ValueError("only challenger/champion artifacts can become active")
        current = self._active[artifact.name]
        self._previous[artifact.name] = current
        self._active[artifact.name] = artifact
        return artifact

    def rollback(self, name: str) -> Artifact:
        previous = self._previous.get(name)
        if previous is None:
            raise RuntimeError(f"no previous version for {name}")
        rolled = Artifact(
            name=previous.name,
            version=previous.version,
            feature_schema_version=previous.feature_schema_version,
            payload=previous.payload,
            state="rolled_back",
        )
        self._previous[name] = self._active[name]
        self._active[name] = Artifact(
            name=previous.name,
            version=previous.version,
            feature_schema_version=previous.feature_schema_version,
            payload=previous.payload,
            state="champion",
        )
        return rolled

    def mark_stale(self, instance_id: str) -> None:
        if instance_id not in self.stale_instances:
            self.stale_instances.append(instance_id)
