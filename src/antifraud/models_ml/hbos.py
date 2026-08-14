from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from antifraud.domain.models import ModelScore


@dataclass
class HbosBundle:
    """Bundle individual por CPF: modelo + scaler + perfis estatísticos + metadados.

    AS-IS: servido via cache em memória, histórico de até ~730 dias.
    Este stub guarda apenas média/desvio por feature para permitir um score
    de anomalia simples (z-score agregado), preservando a interface que um
    bundle real (ex.: HBOS treinado com PyOD) exporia.
    """

    cpf: str
    model_version: str
    feature_means: dict[str, float] = field(default_factory=dict)
    feature_stds: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class HbosBundleCache(ABC):
    """Cache (em memória, por padrão) de bundles HBOS por CPF.

    Ponto de extensão para invalidação distribuída (Evolução prioritária 2):
    implementações reais devem escutar ``model.published`` e invalidar/
    recarregar entradas por CPF ou por versão de modelo.
    """

    @abstractmethod
    def get(self, cpf: str) -> HbosBundle | None:
        raise NotImplementedError

    @abstractmethod
    def put(self, bundle: HbosBundle) -> None:
        raise NotImplementedError

    @abstractmethod
    def invalidate(self, cpf: str | None = None) -> None:
        """Invalida uma entrada específica ou todo o cache quando ``cpf`` é None."""

        raise NotImplementedError


class InMemoryHbosBundleCache(HbosBundleCache):
    def __init__(self) -> None:
        self._bundles: dict[str, HbosBundle] = {}

    def get(self, cpf: str) -> HbosBundle | None:
        return self._bundles.get(cpf)

    def put(self, bundle: HbosBundle) -> None:
        self._bundles[bundle.cpf] = bundle

    def invalidate(self, cpf: str | None = None) -> None:
        if cpf is None:
            self._bundles.clear()
        else:
            self._bundles.pop(cpf, None)


class HbosScorer:
    """Scorer HBOS individual por CPF.

    Não é prova de fraude: score alto representa comportamento atípico em
    relação ao histórico do próprio cliente (sinal comportamental).
    Quando não há bundle (CPF novo / cold start), retorna ``None`` e a
    camada de decisão deve reduzir/zerar o peso do HBOS.
    """

    def __init__(self, cache: HbosBundleCache):
        self._cache = cache

    def score(self, cpf: str, features: dict[str, float]) -> ModelScore | None:
        bundle = self._cache.get(cpf)
        if bundle is None:
            return None

        deviations = []
        for name, value in features.items():
            mean = bundle.feature_means.get(name)
            std = bundle.feature_stds.get(name)
            if mean is None or not std:
                continue
            deviations.append(abs(value - mean) / std)

        if not deviations:
            return ModelScore(
                model_name="hbos_individual",
                model_version=bundle.model_version,
                score=0.0,
                metadata={"note": "sem features comparáveis no bundle"},
            )

        raw = sum(deviations) / len(deviations)
        normalized = 1.0 - (1.0 / (1.0 + raw))  # squashed to [0, 1)
        return ModelScore(
            model_name="hbos_individual",
            model_version=bundle.model_version,
            score=round(normalized, 6),
            metadata={"deviations_evaluated": len(deviations)},
        )
