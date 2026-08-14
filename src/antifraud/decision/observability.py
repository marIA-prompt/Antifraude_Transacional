from __future__ import annotations

import random


class ShadowSampler:
    """Amostragem configurável (1% a 5%) para avaliação em shadow por todas as camadas.

    A amostra shadow NÃO interfere na decisão online; é usada apenas para
    medir divergência, desempenho, calibração e viés entre camadas/modelos.
    Este componente apenas decide o flag da amostra -- a execução completa
    de todas as camadas em modo shadow (mesmo após short-circuit) é
    responsabilidade do chamador (ex.: job assíncrono ou reprocessamento).
    """

    def __init__(self, sample_rate: float = 0.02, rng: random.Random | None = None):
        if not (0.0 <= sample_rate <= 1.0):
            raise ValueError("sample_rate deve estar entre 0.0 e 1.0")
        self._sample_rate = sample_rate
        self._rng = rng or random.Random()

    @property
    def sample_rate(self) -> float:
        return self._sample_rate

    def should_sample(self) -> bool:
        return self._rng.random() < self._sample_rate
