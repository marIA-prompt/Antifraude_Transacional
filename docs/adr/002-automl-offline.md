# ADR-002 — AutoML apenas offline

## Status

Aceito

## Contexto

Azure AutoML é útil para comparar candidatos a HBOS/XGBoost, featurização e
SHAP. Chamada remota no hot path violaria p95 < 100 ms e tornaria a autorização
dependente de serviço externo não determinístico.

## Decisão

AutoML só no ciclo offline: dados maduros → split temporal → treino → avaliação
→ candidate → shadow → canário. O serviço de autorização consome apenas
artefatos já aprovados, versionados e em cache/armazenamento local de baixa
latência.

## Consequências

- Nenhum SDK AutoML no caminho da transação.
- Promoção exige métricas múltiplas, não acurácia isolada.
