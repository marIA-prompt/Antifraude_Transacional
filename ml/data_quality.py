"""Gates de qualidade de dados.

Violação acima do limite configurado BLOQUEIA o pipeline de treino, não apenas
alerta (MLOps: "Falha de qualidade acima do limite configurado deve bloquear o
pipeline de treino").
"""

from __future__ import annotations

import pandas as pd

from ml import schema


class DataQualityError(RuntimeError):
    """Erro que interrompe o pipeline quando um gate de qualidade falha."""


def run_gates(df: pd.DataFrame, config: dict) -> list[str]:
    dq = config["data_quality"]
    failures: list[str] = []
    report: list[str] = []
    n = len(df)

    # 1. CPF em claro nunca pode existir (LGPD) — espelha o teste de contrato.
    forbidden = schema.FORBIDDEN_FIELD_NAMES & {c.lower() for c in df.columns}
    if forbidden:
        failures.append(f"colunas com CPF em claro proibidas: {sorted(forbidden)}")
    report.append(f"ok  nenhuma coluna de CPF em claro ({len(df.columns)} colunas)")

    # 2. Nulos.
    null_rate = df.isna().mean().max() if n else 0.0
    if null_rate > dq["max_null_rate"]:
        failures.append(f"taxa de nulos {null_rate:.3%} > limite {dq['max_null_rate']:.3%}")
    report.append(f"ok  taxa máxima de nulos por coluna: {null_rate:.3%}")

    # 3. Duplicidades de transaction_id.
    dup_rate = df["transaction_id"].duplicated().mean() if n else 0.0
    if dup_rate > dq["max_duplicate_rate"]:
        failures.append(f"duplicidade de transaction_id {dup_rate:.3%} > limite {dq['max_duplicate_rate']:.3%}")
    report.append(f"ok  duplicidade de transaction_id: {dup_rate:.3%}")

    # 4. Timestamps futuros ou inválidos.
    ts = pd.to_datetime(df["occurred_at"], errors="coerce", utc=True)
    invalid_ts = ts.isna().mean() if n else 0.0
    future_ts = (ts > pd.Timestamp.now(tz="UTC")).mean() if n else 0.0
    if invalid_ts > 0:
        failures.append(f"timestamps inválidos: {invalid_ts:.3%}")
    if future_ts > dq["max_future_timestamp_rate"]:
        failures.append(f"timestamps futuros {future_ts:.3%} > limite {dq['max_future_timestamp_rate']:.3%}")
    report.append(f"ok  timestamps inválidos={invalid_ts:.3%} futuros={future_ts:.3%}")

    # 5. Valores fora de faixa.
    neg_amount = (df["amount"] < 0).mean() if n else 0.0
    neg_inst = (df["installments"] < 0).mean() if n else 0.0
    if neg_amount > 0 or neg_inst > 0:
        failures.append(f"valores fora de faixa: amount<0={neg_amount:.3%} installments<0={neg_inst:.3%}")
    report.append(f"ok  amount>=0 e installments>=0")

    # 6. Proporção de CPF novo (transações do primeiro contato do CPF na base).
    first_seen = ~df.sort_values("occurred_at").duplicated("subject_token")
    new_fraction = first_seen.mean() if n else 0.0
    if not (dq["min_new_subject_fraction"] <= new_fraction <= dq["max_new_subject_fraction"]):
        failures.append(
            f"proporção de CPF novo {new_fraction:.2%} fora de "
            f"[{dq['min_new_subject_fraction']:.0%}, {dq['max_new_subject_fraction']:.0%}]"
        )
    report.append(f"ok  proporção de CPF novo: {new_fraction:.2%}")

    # 7. Categorias de rótulo válidas.
    bad_labels = set(df["label_category"].unique()) - set(schema.LABEL_CATEGORIES)
    if bad_labels:
        failures.append(f"categorias de rótulo desconhecidas: {sorted(bad_labels)}")
    report.append(f"ok  categorias de rótulo válidas")

    for line in report:
        print(f"    {line}")
    if failures:
        raise DataQualityError("; ".join(failures))
    return report
