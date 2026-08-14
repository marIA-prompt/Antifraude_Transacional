from __future__ import annotations

from abc import ABC, abstractmethod

from antifraud.domain.models import ModelScore


class XgboostScorer(ABC):
    """Interface do modelo supervisionado global.

    A implementação real depende de rótulos maduros, validação temporal e
    controles contra leakage (fora de escopo deste repositório). Este stub
    expõe apenas o contrato de inferência online: features versionadas in,
    score versionado out.
    """

    @abstractmethod
    def score(self, features: dict[str, float]) -> ModelScore:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_version(self) -> str:
        raise NotImplementedError


class StubXgboostScorer(XgboostScorer):
    """Implementação de referência determinística (NÃO é um modelo treinado).

    Combina algumas features conhecidas em um score em [0, 1] apenas para
    permitir exercitar a cascata de decisão e os testes automatizados.
    """

    def __init__(self, model_version: str = "xgb-stub-0.1.0"):
        self._model_version = model_version

    @property
    def model_version(self) -> str:
        return self._model_version

    def score(self, features: dict[str, float]) -> ModelScore:
        amount_ratio = features.get("amount_to_avg_ratio", 0.0)
        is_new_merchant = features.get("merchant_is_new", 0.0)
        low_history = 1.0 if features.get("customer_history_days", 0.0) < 7 else 0.0

        raw = 0.5 * min(amount_ratio, 5.0) / 5.0 + 0.3 * is_new_merchant + 0.2 * low_history
        score = max(0.0, min(1.0, raw))
        return ModelScore(
            model_name="xgboost_global",
            model_version=self._model_version,
            score=round(score, 6),
        )
