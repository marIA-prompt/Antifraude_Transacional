"""Testes de garantia do pipeline (executável sem framework: python -m ml.selftest).

Comprova as invariantes inegociáveis: LGPD (sem CPF em claro), segurança
temporal das features, gate de qualidade bloqueante e a regra de que
``sem_desfecho`` nunca é usado como negativa.
"""

from __future__ import annotations

import copy

import pandas as pd

from ml import features, schema
from ml.config import load_config
from ml.data_quality import DataQualityError, run_gates
from ml.generate_synthetic import generate
from ml.train import _supervised_slice


def _small_config() -> dict:
    cfg = load_config("ml/config.yaml")
    cfg = copy.deepcopy(cfg)
    cfg["generation"]["n_subjects"] = 400
    return cfg


def main() -> int:
    cfg = _small_config()
    df = generate(cfg)
    checks: list[str] = []

    # 1. LGPD: nenhuma coluna com nome de CPF em claro.
    forbidden = schema.FORBIDDEN_FIELD_NAMES & {c.lower() for c in df.columns}
    assert not forbidden, f"colunas proibidas: {forbidden}"
    assert "subject_token" in df.columns
    checks.append("LGPD: identificador é subject_token, sem CPF em claro")

    # 2. Gate de qualidade passa em dados limpos.
    run_gates(df, cfg)
    checks.append("gate de qualidade aprova dados limpos")

    # 3. Gate BLOQUEIA quando há CPF em claro.
    bad = df.copy()
    bad["cpf"] = "000"
    try:
        run_gates(bad, cfg)
        raise AssertionError("gate deveria ter bloqueado CPF em claro")
    except DataQualityError:
        checks.append("gate BLOQUEIA coluna de CPF em claro")

    # 4. Gate BLOQUEIA duplicidade de transaction_id acima do limite.
    dup = pd.concat([df, df.head(int(len(df) * 0.01))], ignore_index=True)
    try:
        run_gates(dup, cfg)
        raise AssertionError("gate deveria ter bloqueado duplicidade")
    except DataQualityError:
        checks.append("gate BLOQUEIA duplicidade de transaction_id")

    # 5. Segurança temporal: a 1ª transação de cada CPF tem histórico prévio zero.
    feats, _ = features.build_features(df, cfg)
    first = feats.sort_values("occurred_at").groupby("subject_token", sort=False).head(1)
    assert (first["subject_tx_count_prior"] == 0).all(), "1ª transação não pode ter histórico prévio"
    assert (first["region_is_home"] == 1).all(), "região de casa = primeira região observada"
    checks.append("features de histórico são temporalmente seguras (sem leakage)")

    # 6. Modelo de cold start não usa nenhuma feature de histórico do CPF.
    cold_cols = set(features.cold_start_feature_columns(feats))
    assert cold_cols.isdisjoint(set(schema.HISTORY_FEATURES)), "cold start não pode ver histórico do CPF"
    checks.append("cold start não usa features de histórico do CPF (ADR-0002)")

    # 7. sem_desfecho nunca entra como negativa no treino supervisionado.
    feats["y"] = 0
    sup = _supervised_slice(feats)
    assert not sup["label_category"].isin(schema.EXCLUDED_FROM_TRAINING).any()
    assert schema.LABEL_SEM_DESFECHO not in set(sup["label_category"].unique())
    checks.append("sem_desfecho nunca é usado como negativa (MLOps)")

    print("\n".join(f"ok  {c}" for c in checks))
    print(f"\n{len(checks)} garantias verificadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
