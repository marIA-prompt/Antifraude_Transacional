"""Pipeline de treino offline do motor de score antifraude.

Encadeia: qualidade de dados (bloqueante) -> features com segurança temporal ->
split temporal -> treino do GBDT global e do GBDT de cold start -> calibração
isotônica por coorte -> HBOS por CPF -> avaliação por coorte -> artefatos.

Uso:
    python -m ml.train --config ml/config.yaml --data ml/data/transactions.csv --out ml/artifacts
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from ml import evaluate, features, schema
from ml.config import load_config
from ml.data_quality import run_gates
from ml.generate_synthetic import generate
from ml.hbos import HBOS_FEATURES, HbosBundles


def _binary_target(frame: pd.DataFrame) -> pd.Series:
    """1 = fraude_confirmada, 0 = legitima_confirmada; demais => NaN (excluídas)."""
    y = pd.Series(np.nan, index=frame.index)
    y[frame["label_category"].isin(schema.POSITIVE_LABELS)] = 1.0
    y[frame["label_category"].isin(schema.NEGATIVE_LABELS)] = 0.0
    return y


def _supervised_slice(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove rótulos imaturos/ambíguos. sem_desfecho NUNCA vira negativa (MLOps)."""
    keep = frame["label_category"].isin(schema.POSITIVE_LABELS | schema.NEGATIVE_LABELS)
    out = frame.loc[keep].copy()
    out["y"] = _binary_target(out)
    assert not out["label_category"].isin(schema.EXCLUDED_FROM_TRAINING).any(), "sem_desfecho não pode ser usado"
    return out


def _fit_gbdt(X: pd.DataFrame, y: pd.Series, seed: int) -> HistGradientBoostingClassifier:
    model = HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.06,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=seed,
    )
    model.fit(X, y)
    return model


def _fit_isotonic(proba: np.ndarray, y: np.ndarray) -> IsotonicRegression | None:
    if len(np.unique(y)) < 2:
        return None
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(proba, y)
    return iso


def _apply(iso: IsotonicRegression | None, proba: np.ndarray) -> np.ndarray:
    return proba if iso is None else iso.predict(proba)


def run(config: dict, data_path: Path, out_dir: Path) -> dict:
    seed = config["random_seed"]
    split = config["temporal_split"]
    policy = config["policy"]

    # 1. Dados: gera se ausente.
    if not data_path.exists():
        print(f"    dados ausentes; gerando sintético em {data_path}")
        data_path.parent.mkdir(parents=True, exist_ok=True)
        generate(config).to_csv(data_path, index=False)
    df = pd.read_csv(data_path)
    print(f"ok  {len(df):,} transações carregadas de {data_path}")

    # 2. Gates de qualidade (bloqueiam o pipeline em caso de falha).
    print("--- qualidade de dados ---")
    run_gates(df, config)

    # 3. Features com segurança temporal. pop_stats fixado na janela de treino.
    df["_dt"] = pd.to_datetime(df["occurred_at"], utc=True)
    train_mask_raw = df["_dt"] <= pd.Timestamp(split["train_end"], tz="UTC")
    log_amt_train = np.log1p(df.loc[train_mask_raw, "amount"].to_numpy())
    pop_stats = {"log_amount_mean": float(log_amt_train.mean()), "log_amount_std": float(log_amt_train.std() or 1.0)}
    feats, pop_stats = features.build_features(df.drop(columns="_dt"), config, pop_stats)
    print(f"ok  features construídas: {feats.shape[1]} colunas")

    # 4. Split temporal (proibido split aleatório).
    train = feats[feats["occurred_at"] <= pd.Timestamp(split["train_end"], tz="UTC")]
    val = feats[feats["month"] == split["validation_month"]]
    test = feats[feats["month"] == split["test_month"]]
    print(f"ok  split temporal: treino={len(train):,} val={len(val):,} teste={len(test):,}")

    global_cols = features.global_feature_columns(feats)
    cold_cols = features.cold_start_feature_columns(feats)

    is_cold = feats["cohort"].isin(schema.COLD_START_COHORTS)

    # 5. Treino supervisionado.
    train_sup = _supervised_slice(train)
    train_hist = train_sup[~train_sup["cohort"].isin(schema.COLD_START_COHORTS)]
    print(f"ok  treino global: {len(train_hist):,} linhas ({int(train_hist['y'].sum())} fraudes)")
    global_model = _fit_gbdt(train_hist[global_cols], train_hist["y"], seed)
    print(f"ok  treino cold start: {len(train_sup):,} linhas ({int(train_sup['y'].sum())} fraudes)")
    cold_model = _fit_gbdt(train_sup[cold_cols], train_sup["y"], seed)

    # 6. Calibração isotônica na janela de validação, cada modelo na sua coorte.
    val_sup = _supervised_slice(val)
    val_hist = val_sup[~val_sup["cohort"].isin(schema.COLD_START_COHORTS)]
    val_cold = val_sup[val_sup["cohort"].isin(schema.COLD_START_COHORTS)]
    global_iso = _fit_isotonic(global_model.predict_proba(val_hist[global_cols])[:, 1], val_hist["y"].to_numpy()) if len(val_hist) else None
    cold_iso = _fit_isotonic(cold_model.predict_proba(val_cold[cold_cols])[:, 1], val_cold["y"].to_numpy()) if len(val_cold) else None
    print(f"ok  calibração isotônica: global={'sim' if global_iso else 'n/d'} cold_start={'sim' if cold_iso else 'n/d'}")

    # 7. HBOS por CPF (sinal, nunca decisor). Treinado na janela de treino.
    hbos = HbosBundles(HBOS_FEATURES, n_bins=12, min_history=config["cohorts"]["historico_parcial_max_tx"]).fit(train)
    print(f"ok  HBOS: {hbos.coverage_subjects:,} CPFs com bundle elegível")

    # 8. Consolidação por roteamento de coorte + avaliação no teste temporal.
    def consolidated_proba(frame: pd.DataFrame) -> np.ndarray:
        proba = np.zeros(len(frame))
        cold_mask = frame["cohort"].isin(schema.COLD_START_COHORTS).to_numpy()
        if cold_mask.any():
            p = cold_model.predict_proba(frame.loc[cold_mask, cold_cols])[:, 1]
            proba[cold_mask] = _apply(cold_iso, p)
        if (~cold_mask).any():
            p = global_model.predict_proba(frame.loc[~cold_mask, global_cols])[:, 1]
            proba[~cold_mask] = _apply(global_iso, p)
        return proba

    test_sup = _supervised_slice(test)
    test_proba = consolidated_proba(test_sup)
    y_test = test_sup["y"].to_numpy()
    cohorts_test = test_sup["cohort"].to_numpy()

    overall = evaluate.metric_set(y_test, test_proba, policy)
    by_cohort = evaluate.per_cohort_metrics(y_test, test_proba, cohorts_test, policy)

    # HBOS: comprovar peso 0 nas coortes de cold start (ADR-0003).
    hbos_test = hbos.score_frame(test_sup)
    weights = config["cohorts"]["hbos_weight"]
    hbos_cov = {c: float(hbos_test.loc[test_sup["cohort"].to_numpy() == c, "hbos_has_bundle"].mean() or 0.0) for c in schema.COHORTS if (test_sup["cohort"] == c).any()}

    # 9. Persistência de artefatos + registro de modelo.
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "global_model": global_model,
            "cold_model": cold_model,
            "global_iso": global_iso,
            "cold_iso": cold_iso,
            "hbos": hbos,
            "pop_stats": pop_stats,
            "global_cols": global_cols,
            "cold_cols": cold_cols,
        },
        out_dir / "models.joblib",
    )

    version = datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M")
    registry = {
        "schema_version": config["schema_version"],
        "feature_schema_version": f"feat-{config['schema_version']}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "temporal_split": split,
        "cohort_thresholds_version": config["cohorts"]["thresholds_version"],
        "policy_thresholds_version": policy["thresholds_version"],
        "models": {
            "global_model": {"algo": "HistGradientBoosting", "version": f"global-{version}", "state": "candidate", "n_train": int(len(train_hist)), "calibration_version": f"iso-global-{version}" if global_iso else None},
            "cold_start_model": {"algo": "HistGradientBoosting", "version": f"coldstart-{version}", "state": "candidate", "n_train": int(len(train_sup)), "calibration_version": f"iso-cold-{version}" if cold_iso else None},
            "hbos": {"algo": "HBOS-per-subject", "version": f"hbos-{version}", "subjects_with_bundle": hbos.coverage_subjects, "weights_by_cohort": weights},
        },
        "metrics": {"overall": overall, "by_cohort": by_cohort, "hbos_bundle_coverage": hbos_cov},
    }
    (out_dir / "metrics.json").write_text(json.dumps({"overall": overall, "by_cohort": by_cohort}, indent=2, ensure_ascii=False))
    (out_dir / "model_registry.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False))
    _write_report(out_dir / "report.md", config, overall, by_cohort, hbos, hbos_cov, weights, len(train), len(val), len(test))
    print(f"ok  artefatos salvos em {out_dir}")
    return registry


def _fmt(v) -> str:
    return "n/d" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))


def _write_report(path, config, overall, by_cohort, hbos, hbos_cov, weights, n_train, n_val, n_test) -> None:
    lines = ["# Relatório de treino — motor de score antifraude", ""]
    lines.append(f"- Gerado em: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Split temporal: treino={n_train:,} · validação={n_val:,} · teste={n_test:,}")
    lines.append(f"- HBOS: {hbos.coverage_subjects:,} CPFs com bundle elegível")
    lines.append("")
    lines.append("## Métricas mínimas de promoção — teste temporal (geral)")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("|---|---|")
    for k in ["n", "n_fraude", "pr_auc", "roc_auc", "recall", "precision", "fpr", "fnr", "brier", "challenge_rate", "approve_rate", "deny_rate"]:
        lines.append(f"| {k} | {_fmt(overall.get(k))} |")
    lines.append("")
    lines.append("## Métricas por coorte de cold start (ADR-0003)")
    lines.append("")
    lines.append("| Coorte | n | fraudes | PR-AUC | ROC-AUC | recall | precisão | FPR | challenge | HBOS peso | HBOS cobertura |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for cohort in schema.COHORTS:
        m = by_cohort.get(cohort)
        if not m:
            continue
        lines.append(
            f"| {cohort} | {m['n']} | {m['n_fraude']} | {_fmt(m['pr_auc'])} | {_fmt(m['roc_auc'])} | "
            f"{_fmt(m['recall'])} | {_fmt(m['precision'])} | {_fmt(m['fpr'])} | {_fmt(m['challenge_rate'])} | "
            f"{weights.get(cohort)} | {_fmt(hbos_cov.get(cohort))} |"
        )
    lines.append("")
    lines.append("> HBOS tem peso 0 em `sem_historico`/`historico_minimo` (ADR-0003): sinal comportamental, nunca decisor.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Treina os modelos do motor antifraude com dados sintéticos.")
    parser.add_argument("--config", default="ml/config.yaml")
    parser.add_argument("--data", default="ml/data/transactions.csv")
    parser.add_argument("--out", default="ml/artifacts")
    args = parser.parse_args()

    config = load_config(args.config)
    registry = run(config, Path(args.data), Path(args.out))
    o = registry["metrics"]["overall"]
    print("\n=== resumo (teste temporal) ===")
    print(f"PR-AUC={_fmt(o['pr_auc'])} ROC-AUC={_fmt(o['roc_auc'])} recall={_fmt(o['recall'])} precisão={_fmt(o['precision'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
