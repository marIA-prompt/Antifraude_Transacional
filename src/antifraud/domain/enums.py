from __future__ import annotations

from enum import Enum


class Decision(str, Enum):
    """Decisão de negócio para uma transação ou para o desfecho de um challenge."""

    APPROVE = "approve"
    CHALLENGE = "challenge"
    DENY = "deny"
    ESCALATE = "escalate"
    REJECT = "reject"
    """Erro controlado de validação de payload (não é uma decisão de risco)."""


class Layer(str, Enum):
    """Camadas do fluxo AS-IS de decisão em cascata.

    A ordem aqui reflete o fluxo documentado:
    validação -> features -> HBOS -> regras/hard rules -> XGBoost -> decisão.
    """

    PAYLOAD_VALIDATION = "payload_validation"
    FEATURE_ENGINEERING = "feature_engineering"
    HBOS_INDIVIDUAL = "hbos_individual"
    HARD_RULES = "hard_rules"
    BUSINESS_RULES = "business_rules"
    COLD_START_POLICY = "cold_start_policy"
    XGBOOST_GLOBAL = "xgboost_global"
    CONSOLIDATION = "consolidation"


class ValidatorOutcome(str, Enum):
    """Resultado possível de um validador do workflow de challenge.

    Usado tanto para o resultado funcional (approve/deny/escalate) quanto
    para o status de execução (timeout/error/fallback), mantidos em campos
    separados no ``ValidatorResult``.
    """

    APPROVE = "approve"
    DENY = "deny"
    ESCALATE = "escalate"


class ValidatorExecutionStatus(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
    FALLBACK = "fallback"
    CIRCUIT_OPEN = "circuit_open"


class ModelRegistryState(str, Enum):
    """Estados recomendados no model registry (ver Estratégia de rollout)."""

    CANDIDATE = "candidate"
    CHALLENGER = "challenger"
    CHAMPION = "champion"
    DEPRECATED = "deprecated"
    ROLLED_BACK = "rolled_back"


class LabelMaturity(str, Enum):
    """Categorias de maturação de rótulos (não classificar sem_desfecho como legítima)."""

    FRAUDE_CONFIRMADA = "fraude_confirmada"
    FRAUDE_SUSPEITA = "fraude_suspeita"
    EM_DISPUTA = "em_disputa"
    LEGITIMA_CONFIRMADA = "legitima_confirmada"
    SEM_DESFECHO = "sem_desfecho"


class ApiConsumerRole(str, Enum):
    """Perfis de autorização para a API v2 (explicabilidade)."""

    BASIC = "basic"
    ANALYST = "analyst"
    ADMIN = "admin"
