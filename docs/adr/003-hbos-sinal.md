# ADR-003 — HBOS é sinal de anomalia

## Status

Aceito

## Contexto

HBOS compara a transação ao histórico do próprio CPF. Score alto significa
atipicidade. Clientes legítimos com comportamento variável geram falso positivo
se HBOS for tratado como classificador de fraude.

## Decisão

HBOS nunca é prova de fraude. Entra na consolidação como sinal ponderado,
com peso nulo ou reduzido em cold start / histórico insuficiente. Deny
determinístico exige hard rule crítica ou política explícita, não o HBOS sozinho.

## Consequências

- Reason codes separam `anomaly_hbos` de `fraud_xgboost` e `hard_rule_*`.
- XGBoost e regras cobrem CPF novo.
