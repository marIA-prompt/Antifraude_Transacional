"""Schema dos dados de transação e definições de treino.

Fiel aos contratos versionados (contracts/openapi/score-api.yaml e
contracts/events/fraud.challenge.created.schema.json): o titular é sempre
identificado por ``subject_token`` (CPF tokenizado), nunca por CPF em claro.
"""

from __future__ import annotations

# Campos que NÃO podem existir em dado algum: CPF precisa trafegar tokenizado (LGPD).
# Espelha scripts/validate_contracts.py::FORBIDDEN_FIELD_NAMES.
FORBIDDEN_FIELD_NAMES = {"cpf", "cpf_titular", "document_number", "taxpayer_id"}

# Colunas brutas da transação (equivalem ao ScoreRequest + transaction_context do evento).
RAW_COLUMNS = [
    "transaction_id",
    "subject_token",
    "occurred_at",
    "amount",
    "currency",
    "channel",
    "product",
    "transaction_type",
    "installments",
    "merchant_id",
    "mcc",
    "merchant_is_new_for_subject",
    "device_fingerprint_token",
    "device_is_new_for_subject",
    "geo_country",
    "geo_region",
    "geo_precision",
    "ip_hash",
    "label_category",  # rótulo maturado (ver categorias abaixo)
    "is_fraud",        # verdade oculta para avaliação; indisponível no scoring online
]

# Domínios categóricos (baixa cardinalidade → one-hot no pipeline).
CHANNELS = ["ecommerce", "pos", "recurring", "atm", "wallet"]
PRODUCTS = ["credit", "private_label"]
TRANSACTION_TYPES = ["purchase", "withdrawal", "bill_payment", "subscription"]
GEO_PRECISIONS = ["gps", "cell", "ip", "none"]
# Faixas de MCC agregadas (proxy de risco por tipo de comércio).
MCC_BUCKETS = ["varejo", "servicos", "viagem", "digital", "saque", "aposta"]

# --- Categorias de rótulo (MLOps: maturação de rótulos) ---
LABEL_FRAUDE_CONFIRMADA = "fraude_confirmada"
LABEL_FRAUDE_SUSPEITA = "fraude_suspeita"
LABEL_EM_DISPUTA = "em_disputa"
LABEL_LEGITIMA_CONFIRMADA = "legitima_confirmada"
LABEL_SEM_DESFECHO = "sem_desfecho"

LABEL_CATEGORIES = [
    LABEL_FRAUDE_CONFIRMADA,
    LABEL_FRAUDE_SUSPEITA,
    LABEL_EM_DISPUTA,
    LABEL_LEGITIMA_CONFIRMADA,
    LABEL_SEM_DESFECHO,
]

# Mapeamento para alvo supervisionado binário.
# Regra inegociável (MLOps): sem_desfecho NUNCA é negativa. em_disputa/fraude_suspeita
# ficam de fora do treino supervisionado por ainda não terem desfecho estável.
POSITIVE_LABELS = {LABEL_FRAUDE_CONFIRMADA}
NEGATIVE_LABELS = {LABEL_LEGITIMA_CONFIRMADA}
EXCLUDED_FROM_TRAINING = {LABEL_SEM_DESFECHO, LABEL_EM_DISPUTA, LABEL_FRAUDE_SUSPEITA}

# Coortes de cold start (ADR-0003).
COHORTS = ["sem_historico", "historico_minimo", "historico_parcial", "historico_pleno"]
COLD_START_COHORTS = {"sem_historico", "historico_minimo"}


def cohort_for(prior_tx_count: int, cohorts_cfg: dict) -> str:
    """Faixa de histórico a partir do nº de transações prévias do CPF (ADR-0003)."""
    if prior_tx_count <= 0:
        return "sem_historico"
    if prior_tx_count <= cohorts_cfg["historico_minimo_max_tx"]:
        return "historico_minimo"
    if prior_tx_count <= cohorts_cfg["historico_parcial_max_tx"]:
        return "historico_parcial"
    return "historico_pleno"


# --- Conjuntos de features ---
# Cold start: apenas atributos da transação/device/merchant/geo e agregados de
# população — SEM nenhuma feature derivada do histórico do próprio CPF (ADR-0002).
COLD_START_FEATURES = [
    "log_amount",
    "amount_zscore_pop",
    "hour",
    "is_night",
    "dow",
    "is_weekend",
    "installments",
    "merchant_is_new_for_subject",
    "device_is_new_for_subject",
    "geo_is_domestic",
]  # + colunas one-hot de channel/product/transaction_type/geo_precision/mcc_bucket

# Modelo global: cold start + features derivadas do histórico do CPF.
HISTORY_FEATURES = [
    "subject_tx_count_prior",
    "subject_amount_mean_prior",
    "amount_ratio_to_subject_mean",
    "secs_since_last_tx",
    "tx_count_24h",
    "tx_count_7d",
    "distinct_devices_prior",
    "distinct_regions_prior",
    "region_is_home",
]

ONEHOT_COLUMNS = ["channel", "product", "transaction_type", "geo_precision", "mcc_bucket"]
