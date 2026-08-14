# Política de cold start (Evolução prioritária 3)

## Lacuna/Risco (AS-IS)

Aprovar por padrão CPF novo reduz atrito, mas aumenta exposição a fraude na ausência de
histórico comportamental (o HBOS individual não tem base de comparação).

## TO-BE implementado neste repositório

`src/antifraud/coldstart/policy.py` (`ColdStartPolicy`, `ColdStartThresholds`):

```text
CPF novo (profile.is_cold_start(): poucas transações OU pouco histórico em dias)
  + hard rule crítica     → deny            (reason_code: cold_start_hard_rule)
  + baixo valor           → approve         (reason_code: cold_start_low_value_monitored)
  + valor intermediário   → challenge       (reason_code: cold_start_intermediate_value_stepup)
  + alto valor            → escalate        (reason_code: cold_start_high_value)

Em qualquer caso de cold start:
  → peso do HBOS multiplicado por `hbos_weight_reduction_factor` (default 0.0 = peso nulo)
  → peso do XGBoost multiplicado por `global_model_weight_boost` (default 1.3)
  → reason_code "cold_start" sempre incluído
```

A política é aplicada dentro de `DecisionCascade.decide` (após hard rules e regras de
negócio, antes do XGBoost), e o `DecisionTrace.is_cold_start` fica disponível tanto para a
API v2 quanto para o evento `fraud.challenge.created`.

Os thresholds (`ColdStartThresholds.low_value_ceiling`, `high_value_floor`,
`hbos_weight_reduction_factor`, `global_model_weight_boost`) são parâmetros construtores —
em produção devem vir de um config store/feature flag por canal/produto/tipo de transação,
sem exigir redeploy (o objeto é injetável e desacoplado do restante da cascata exatamente para
viabilizar essa configuração externa).

## O que este repositório NÃO implementa (fora de escopo)

- Persistência real de perfil de cliente com atualização após cada transação (o
  `InMemoryCustomerProfileRepository` não é atualizado automaticamente pelo `DecisionCascade`;
  isso seria responsabilidade de um pipeline de atualização de perfil/feature store).
- Métricas por coorte (CPF novo vs. histórico), revisão periódica de impacto em atrito/receita/
  perda por fraude, e o mecanismo de configuração dinâmica de thresholds sem redeploy
  (config store/feature flag) em si.

## Critérios de aceite

- **Métricas separadas para CPF novo e CPF com histórico**: o `DecisionTrace.is_cold_start`
  permite segmentar qualquer análise offline por essa dimensão; o cálculo agregado das
  métricas (taxas de fraude, challenge, deny, aprovação legítima, reversão) é lacuna aberta.
- **Thresholds configuráveis sem redeploy**: `ColdStartThresholds` é injetável via construtor;
  a integração com um config store dinâmico é lacuna aberta.
- Cobertura de teste: `tests/test_cold_start_policy.py` (todas as combinações de valor/hard
  rule/pesos) e `tests/test_service_end_to_end.py` (efeito ponta a ponta no `AntifraudService`).
