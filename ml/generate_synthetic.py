"""Gerador de dados sintéticos de transações de cartão (LGPD-safe).

Produz um dataset fictício, porém com comportamento estatístico realista de
antifraude: fraude rara (~1%), sazonalidade horária, perfis por cliente,
cold start de CPF novo e rótulos maturados. Nenhum dado pessoal real é usado;
o titular é sempre um token opaco (``subject_token``).

Uso:
    python -m ml.generate_synthetic --config ml/config.yaml --out ml/data
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from ml import schema
from ml.config import load_config


def _hash_token(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def _label_from_fraud(is_fraud: np.ndarray, immature: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Deriva a categoria de rótulo maturada a partir da verdade oculta.

    Transações imaturas (recentes demais para desfecho) viram ``sem_desfecho``,
    independentemente de serem fraude — refletindo a maturação real de rótulos.
    """
    labels = np.empty(len(is_fraud), dtype=object)
    for i in range(len(is_fraud)):
        if immature[i]:
            labels[i] = schema.LABEL_SEM_DESFECHO
            continue
        if is_fraud[i]:
            r = rng.random()
            if r < 0.80:
                labels[i] = schema.LABEL_FRAUDE_CONFIRMADA
            elif r < 0.92:
                labels[i] = schema.LABEL_EM_DISPUTA
            else:
                labels[i] = schema.LABEL_FRAUDE_SUSPEITA
        else:
            r = rng.random()
            if r < 0.90:
                labels[i] = schema.LABEL_LEGITIMA_CONFIRMADA
            else:
                labels[i] = schema.LABEL_SEM_DESFECHO
    return labels


def generate(config: dict) -> pd.DataFrame:
    gen = config["generation"]
    rng = np.random.default_rng(config["random_seed"])

    n_subjects = int(gen["n_subjects"])
    start = pd.Timestamp(gen["start_date"], tz="UTC")
    end = start + pd.DateOffset(months=int(gen["months"]))
    total_seconds = int((end - start).total_seconds())

    # Perfil comportamental por CPF (tokenizado).
    subject_tokens = np.array([_hash_token("subj", f"cpf-ficticio-{i:07d}") for i in range(n_subjects)])
    home_region = rng.integers(0, 27, size=n_subjects)  # 27 UFs
    typical_log_amount = rng.normal(4.6, 0.6, size=n_subjects)  # ~R$100 mediano
    primary_channel = rng.choice(len(schema.CHANNELS), size=n_subjects, p=[0.42, 0.34, 0.12, 0.05, 0.07])
    primary_product = rng.choice(len(schema.PRODUCTS), size=n_subjects, p=[0.7, 0.3])
    active_hour = rng.integers(9, 22, size=n_subjects)  # pico de atividade legítima

    # CPFs "novos" entram tarde na janela → geram coorte de cold start.
    new_mask = rng.random(n_subjects) < float(gen["new_subject_fraction"])
    entry_frac = np.where(new_mask, rng.uniform(0.75, 0.98, n_subjects), rng.uniform(0.0, 0.4, n_subjects))
    subject_entry = start + pd.to_timedelta(entry_frac * total_seconds, unit="s")

    # Volume de transações por CPF (novos têm menos).
    lam = np.where(new_mask, rng.uniform(1, 6, n_subjects), rng.uniform(8, 60, n_subjects))
    n_tx = rng.poisson(lam).clip(min=1)

    base_fraud_rate = float(gen["base_fraud_rate"])
    device_pool = np.array([_hash_token("dev", f"device-{i}") for i in range(n_subjects * 2)])

    rows = []
    for s in range(n_subjects):
        k = int(n_tx[s])
        # Timestamps entre a entrada do CPF e o fim da janela.
        entry_s = int((subject_entry[s] - start).total_seconds())
        ts_offsets = rng.integers(entry_s, total_seconds, size=k)
        ts_offsets.sort()
        occurred = start + pd.to_timedelta(ts_offsets, unit="s")

        # Dispositivo primário do cliente + eventuais novos.
        primary_device = device_pool[s]
        for j in range(k):
            t = occurred[j]
            is_first = j == 0

            # Sinais de risco independentes (device novo, merchant novo, geo fora de casa, madrugada, alto valor).
            device_new = is_first or (rng.random() < 0.06)
            device = primary_device if not device_new else device_pool[rng.integers(0, len(device_pool))]
            merchant_new = is_first or (rng.random() < 0.25)
            hour = int(t.hour)
            night = hour <= 5 or hour >= 23
            region = int(home_region[s]) if rng.random() < 0.9 else int(rng.integers(0, 27))
            geo_domestic = rng.random() < 0.985
            amount = float(np.exp(rng.normal(typical_log_amount[s], 0.5)))

            # Probabilidade de fraude cresce com os sinais de risco (para os modelos aprenderem).
            logit = -6.0 + float(gen.get("_bias", 0.0))
            logit += 1.4 * device_new + 0.5 * merchant_new + 1.1 * night
            logit += 0.9 * (region != home_region[s]) + 1.6 * (not geo_domestic)
            logit += 0.8 * (amount > np.exp(typical_log_amount[s] + 1.2))
            logit += 0.6 * new_mask[s]  # CPF novo é mais exposto
            p_fraud = 1.0 / (1.0 + np.exp(-logit))
            # Reescala para atingir a taxa-base alvo aproximada.
            p_fraud = min(0.97, p_fraud * (base_fraud_rate / 0.0025))
            is_fraud = rng.random() < p_fraud

            if is_fraud:
                amount *= rng.uniform(1.5, 6.0)  # fraude tende a valores atípicos
                installments = int(rng.choice([1, 1, 1, 12, 18], p=[0.4, 0.2, 0.1, 0.2, 0.1]))
                ttype = int(rng.choice(len(schema.TRANSACTION_TYPES), p=[0.5, 0.3, 0.1, 0.1]))
                mcc_bucket = int(rng.choice(len(schema.MCC_BUCKETS), p=[0.15, 0.1, 0.2, 0.2, 0.2, 0.15]))
            else:
                installments = int(rng.choice([1, 2, 3, 6, 10], p=[0.55, 0.15, 0.15, 0.1, 0.05]))
                ttype = int(primary_product[s] == 1) * 0 + int(
                    rng.choice(len(schema.TRANSACTION_TYPES), p=[0.7, 0.05, 0.15, 0.1])
                )
                mcc_bucket = int(rng.choice(len(schema.MCC_BUCKETS), p=[0.4, 0.25, 0.08, 0.15, 0.1, 0.02]))

            channel = int(primary_channel[s]) if rng.random() < 0.75 else int(rng.integers(0, len(schema.CHANNELS)))
            precision = int(rng.choice(len(schema.GEO_PRECISIONS), p=[0.45, 0.3, 0.2, 0.05]))

            rows.append(
                {
                    "transaction_id": str(uuid.UUID(bytes=rng.bytes(16))),
                    "subject_token": subject_tokens[s],
                    "occurred_at": t,
                    "amount": round(amount, 2),
                    "currency": gen["currency"],
                    "channel": schema.CHANNELS[channel],
                    "product": schema.PRODUCTS[int(primary_product[s])],
                    "transaction_type": schema.TRANSACTION_TYPES[ttype],
                    "installments": installments,
                    "merchant_id": _hash_token("mer", f"m-{rng.integers(0, 40000)}"),
                    "mcc": schema.MCC_BUCKETS[mcc_bucket],
                    "merchant_is_new_for_subject": bool(merchant_new),
                    "device_fingerprint_token": device,
                    "device_is_new_for_subject": bool(device_new),
                    "geo_country": "BR" if geo_domestic else rng.choice(["US", "PT", "AR", "PY"]),
                    "geo_region": f"BR-{region:02d}" if geo_domestic else "INTL",
                    "geo_precision": schema.GEO_PRECISIONS[precision],
                    "ip_hash": _hash_token("ip", f"{rng.integers(0, 2**32)}"),
                    "is_fraud": bool(is_fraud),
                }
            )

    df = pd.DataFrame(rows).sort_values("occurred_at").reset_index(drop=True)

    # Maturação: transações nas últimas `label_maturation_days` da janela ficam sem desfecho.
    mat_days = int(config["temporal_split"]["label_maturation_days"])
    cutoff = end - pd.Timedelta(days=mat_days)
    immature = (df["occurred_at"] >= cutoff).to_numpy()
    df["label_category"] = _label_from_fraud(df["is_fraud"].to_numpy(), immature, rng)

    df["occurred_at"] = df["occurred_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df[schema.RAW_COLUMNS]


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera dataset sintético de transações antifraude.")
    parser.add_argument("--config", default="ml/config.yaml")
    parser.add_argument("--out", default="ml/data")
    args = parser.parse_args()

    config = load_config(args.config)
    df = generate(config)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "transactions.csv"
    df.to_csv(csv_path, index=False)
    print(f"ok  {len(df):,} transações -> {csv_path}")
    try:
        parquet_path = out_dir / "transactions.parquet"
        df.to_parquet(parquet_path, index=False)
        print(f"ok  espelho colunar -> {parquet_path}")
    except Exception as exc:  # pyarrow ausente: CSV é suficiente
        print(f"aviso: parquet não gerado ({exc})")

    fraud = (df["label_category"] == schema.LABEL_FRAUDE_CONFIRMADA).mean()
    print(f"ok  fraude_confirmada={fraud:.3%} | sem_desfecho={(df['label_category'] == schema.LABEL_SEM_DESFECHO).mean():.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
