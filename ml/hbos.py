"""HBOS individual por CPF — sinal comportamental, nunca decisor (ADR-0002).

Treino offline barato por cliente; inferência a partir de histogramas em memória.
A contribuição por feature sai do próprio histograma, alimentando reason codes
sem custo de SHAP em tempo real. CPF sem histórico suficiente não recebe bundle
(peso zero no cold start — ADR-0003).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HBOS_FEATURES = ["log_amount", "hour", "installments"]


class HbosBundles:
    """Coleção de bundles HBOS, um por CPF elegível."""

    def __init__(self, features: list[str], n_bins: int, min_history: int):
        self.features = features
        self.n_bins = n_bins
        self.min_history = min_history
        self.bundles: dict[str, dict] = {}

    def fit(self, train_feats: pd.DataFrame) -> "HbosBundles":
        for subject, idx in train_feats.groupby("subject_token", sort=False).indices.items():
            block = train_feats.iloc[idx]
            if len(block) < self.min_history:
                continue  # sem histórico suficiente => sem bundle (cold start)
            bundle = {}
            for feat in self.features:
                values = block[feat].to_numpy(dtype=float)
                lo, hi = np.nanmin(values), np.nanmax(values)
                if not np.isfinite(lo) or hi <= lo:
                    hi = lo + 1.0
                edges = np.linspace(lo, hi, self.n_bins + 1)
                counts, _ = np.histogram(values, bins=edges)
                density = counts / max(counts.sum(), 1)
                # Densidade suavizada (evita -log(0)); log-densidade normalizada.
                smoothed = np.clip(density, 1e-6, None)
                log_dens = np.log(smoothed / smoothed.max())
                bundle[feat] = {"edges": edges, "neg_log_dens": -log_dens}
            self.bundles[subject] = bundle
        return self

    def _score_row(self, subject: str, row: pd.Series) -> tuple[float | None, dict]:
        bundle = self.bundles.get(subject)
        if bundle is None:
            return None, {}
        total = 0.0
        contributions = {}
        for feat, hist in bundle.items():
            edges = hist["edges"]
            b = int(np.clip(np.searchsorted(edges, row[feat], side="right") - 1, 0, len(edges) - 2))
            contrib = float(hist["neg_log_dens"][b])
            contributions[feat] = contrib
            total += contrib
        return total, contributions

    def score_frame(self, feats: pd.DataFrame) -> pd.DataFrame:
        scores = np.full(len(feats), np.nan)
        has_bundle = np.zeros(len(feats), dtype=bool)
        subjects = feats["subject_token"].to_numpy()
        for i in range(len(feats)):
            score, _ = self._score_row(subjects[i], feats.iloc[i])
            if score is not None:
                scores[i] = score
                has_bundle[i] = True
        # Normaliza para [0,1] como sinal (não é probabilidade de fraude).
        finite = scores[np.isfinite(scores)]
        scale = np.percentile(finite, 99) if finite.size else 1.0
        scale = scale or 1.0
        norm = 1.0 - np.exp(-scores / scale)
        return pd.DataFrame({"hbos_score": scores, "hbos_signal": norm, "hbos_has_bundle": has_bundle}, index=feats.index)

    @property
    def coverage_subjects(self) -> int:
        return len(self.bundles)
