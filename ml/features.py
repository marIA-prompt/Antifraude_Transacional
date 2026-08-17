"""Feature engineering com segurança temporal (sem leakage).

Toda feature derivada do histórico do CPF usa apenas transações estritamente
anteriores à transação corrente (MLOps: "Uma transação histórica não pode usar
dados disponíveis apenas após sua ocorrência"). As features do modelo de cold
start não tocam o histórico do CPF (ADR-0002).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml import schema

_DAY = 86400.0
_SENTINEL_GAP = 3650 * _DAY  # "nunca visto antes"


def _subject_history_features(df: pd.DataFrame) -> pd.DataFrame:
    """Agregados por CPF sobre a janela estritamente anterior a cada transação."""
    out = {
        "subject_tx_count_prior": np.zeros(len(df)),
        "subject_amount_mean_prior": np.full(len(df), np.nan),
        "secs_since_last_tx": np.full(len(df), _SENTINEL_GAP),
        "tx_count_24h": np.zeros(len(df)),
        "tx_count_7d": np.zeros(len(df)),
        "distinct_devices_prior": np.zeros(len(df)),
        "distinct_regions_prior": np.zeros(len(df)),
        "region_is_home": np.zeros(len(df)),
    }
    ts_all = df["occurred_at"].astype("int64").to_numpy() / 1e9  # segundos epoch
    amt_all = df["amount"].to_numpy()
    dev_all = df["device_fingerprint_token"].to_numpy()
    reg_all = df["geo_region"].to_numpy()

    for _, idx in df.groupby("subject_token", sort=False).indices.items():
        idx = np.sort(idx)
        ts = ts_all[idx]
        amt = amt_all[idx]
        dev = dev_all[idx]
        reg = reg_all[idx]
        home_region = reg[0]  # primeira região observada = "casa" (temporalmente válida)

        seen_dev: set = set()
        seen_reg: set = set()
        for pos, row in enumerate(idx):
            out["subject_tx_count_prior"][row] = pos
            if pos > 0:
                out["subject_amount_mean_prior"][row] = amt[:pos].mean()
                out["secs_since_last_tx"][row] = ts[pos] - ts[pos - 1]
                lo24 = np.searchsorted(ts[:pos], ts[pos] - _DAY, side="left")
                lo7 = np.searchsorted(ts[:pos], ts[pos] - 7 * _DAY, side="left")
                out["tx_count_24h"][row] = pos - lo24
                out["tx_count_7d"][row] = pos - lo7
            out["distinct_devices_prior"][row] = len(seen_dev)
            out["distinct_regions_prior"][row] = len(seen_reg)
            out["region_is_home"][row] = float(reg[pos] == home_region)
            seen_dev.add(dev[pos])
            seen_reg.add(reg[pos])

    res = pd.DataFrame(out, index=df.index)
    pop_mean_amount = df["amount"].mean()
    res["subject_amount_mean_prior"] = res["subject_amount_mean_prior"].fillna(pop_mean_amount)
    res["amount_ratio_to_subject_mean"] = df["amount"].to_numpy() / res["subject_amount_mean_prior"].to_numpy()
    return res


def build_features(df: pd.DataFrame, config: dict, pop_stats: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Constrói a matriz de features. Retorna (frame, pop_stats)."""
    df = df.copy()
    df["occurred_at"] = pd.to_datetime(df["occurred_at"], utc=True)
    df = df.sort_values("occurred_at").reset_index(drop=True)

    ts = df["occurred_at"].dt
    feats = pd.DataFrame(index=df.index)
    feats["log_amount"] = np.log1p(df["amount"].to_numpy())
    if pop_stats is None:
        pop_stats = {"log_amount_mean": float(feats["log_amount"].mean()), "log_amount_std": float(feats["log_amount"].std() or 1.0)}
    feats["amount_zscore_pop"] = (feats["log_amount"] - pop_stats["log_amount_mean"]) / pop_stats["log_amount_std"]
    feats["hour"] = ts.hour.to_numpy()
    feats["is_night"] = ((ts.hour <= 5) | (ts.hour >= 23)).astype(int).to_numpy()
    feats["dow"] = ts.dayofweek.to_numpy()
    feats["is_weekend"] = (ts.dayofweek >= 5).astype(int).to_numpy()
    feats["installments"] = df["installments"].to_numpy()
    feats["merchant_is_new_for_subject"] = df["merchant_is_new_for_subject"].astype(int).to_numpy()
    feats["device_is_new_for_subject"] = df["device_is_new_for_subject"].astype(int).to_numpy()
    feats["geo_is_domestic"] = (df["geo_country"] == "BR").astype(int).to_numpy()

    # One-hot de categóricas de baixa cardinalidade, com categorias fixas.
    categories = {
        "channel": schema.CHANNELS,
        "product": schema.PRODUCTS,
        "transaction_type": schema.TRANSACTION_TYPES,
        "geo_precision": schema.GEO_PRECISIONS,
        "mcc_bucket": schema.MCC_BUCKETS,
    }
    onehot_source = df.rename(columns={"mcc": "mcc_bucket"})
    for col, cats in categories.items():
        series = pd.Categorical(onehot_source[col], categories=cats)
        dummies = pd.get_dummies(series, prefix=col).astype(int)
        dummies.index = df.index
        feats = pd.concat([feats, dummies], axis=1)

    # Features de histórico do CPF (somente para o modelo global).
    hist = _subject_history_features(df)
    feats = pd.concat([feats, hist], axis=1)

    # Coorte de cold start (ADR-0003), a partir do nº de transações prévias.
    prior = hist["subject_tx_count_prior"].astype(int).to_numpy()
    feats["cohort"] = [schema.cohort_for(int(p), config["cohorts"]) for p in prior]

    # Metadados carregados junto (não são features).
    feats["subject_token"] = df["subject_token"].to_numpy()
    feats["occurred_at"] = df["occurred_at"].to_numpy()
    feats["month"] = ts.strftime("%Y-%m").to_numpy()
    feats["label_category"] = df["label_category"].to_numpy()
    feats["is_fraud"] = df["is_fraud"].astype(int).to_numpy()
    return feats, pop_stats


def onehot_feature_names(feats: pd.DataFrame) -> list[str]:
    names = []
    for col in schema.ONEHOT_COLUMNS:
        names.extend([c for c in feats.columns if c.startswith(f"{col}_")])
    return names


def global_feature_columns(feats: pd.DataFrame) -> list[str]:
    return schema.COLD_START_FEATURES + onehot_feature_names(feats) + schema.HISTORY_FEATURES


def cold_start_feature_columns(feats: pd.DataFrame) -> list[str]:
    return schema.COLD_START_FEATURES + onehot_feature_names(feats)
