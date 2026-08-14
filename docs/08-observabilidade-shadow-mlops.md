# 08 — Observabilidade, shadow e MLOps

## Short-circuit e registro obrigatório

### AS-IS

Camadas podem encerrar cedo. Não há garantia de registro das camadas puladas.

### Lacuna / risco

Viés de seleção no retreino; impossibilidade de calibrar HBOS/XGBoost na
população aprovada pela Regra 83.

### TO-BE — envelope de auditoria por transação

```text
layers_executed
layers_skipped
terminated_by
score_hbos
score_xgboost
score_consolidated
rules_triggered
signals
model_versions
decision_final
fallback_reason (se houver)
shadow_evaluated (bool)
```

CPF e dados sensíveis: tokenizados / minimizados no log exportável.

## Shadow

Amostra configurável **1% a 5%** das transações (incluindo as que short-circuitariam)
é avaliada por todas as camadas **sem** interferir na decisão online.

Uso: divergência HBOS vs XGBoost vs regras, latência extra (fora do p95 de
produção), calibração e viés.

A latência do shadow **não** entra no SLA do hot path (execução async ou
best-effort após responder).

## Qualidade de dados (contínua)

Nulos, duplicidades, replays, estornos, timestamps futuros, valores fora de
faixa, geo inválida, mudança de schema, proporção de CPF novo, cobertura por
canal, features com risco de leakage temporal.

## Validação temporal

```text
Treino: jan–set
Validação: out
Teste temporal: nov
Produção / monitoramento: dez em diante
```

Uma transação histórica não pode usar status, chargeback ou feature disponíveis
somente depois do seu timestamp.

## Maturação de rótulos

```text
fraude_confirmada
fraude_suspeita
em_disputa
legitima_confirmada
sem_desfecho
```

**Proibido:** promover `sem_desfecho` a legítima automaticamente.

## Drift

PSI, KS por feature, distribuição de scores, nulos, volume, ticket médio,
horários, parcelas, canais, estabelecimentos, regiões, dispositivos, taxa de
CPF novo, fraude confirmada por banda de score, divergência HBOS / XGBoost /
challenger.

## AutoML (offline)

Permitido para classificação/regressão, featurização, comparação com HBOS e
XGBoost, SHAP, champion/challenger.

**Proibido:**

```text
Transação online → chamada remota ao AutoML → autorização
```

## Métricas mínimas para promoção

PR-AUC, ROC-AUC, recall de fraude, precisão, FPR, FNR, taxa de challenge,
taxa de aprovação legítima, calibração, custo evitado, fraude residual,
latência, estabilidade temporal, métricas por coorte, explicabilidade, custo
operacional.

Nenhum modelo é promovido só por acurácia.

Estados no registry: `candidate` → `challenger` → `champion` (ou `rolled_back`,
`deprecated`).

Promoção considera também calibração, explicabilidade, latência, viés, custo,
falsos positivos e impacto em experiência — não só ganho estatístico.

## Critérios de aceite

- 100% das inferências de produção com versão de modelo registrada.
- Shadow não altera `decision_final`.
- Job de qualidade falha o treino se leakage temporal for detectado nos testes
  de pipeline (quando o pipeline existir).
- Testes de envelope e shadow: `tests/test_observability.py`.
