# Invalidação de cache e publicação de modelos (Evolução prioritária 2)

## Lacuna/Risco (AS-IS)

Depois de um retreinamento, o serviço pode continuar usando versões antigas em cache,
exigindo restart ou limpeza manual — não há model registry nem invalidação automática
documentados no AS-IS.

## TO-BE implementado neste repositório

```text
ModelRegistry.register()               (candidate)
  → ModelRegistry.promote()             (champion; anterior vira deprecated)
    → ModelPublishedEvent               (model.published)
      → ModelCacheInvalidationService.handle_model_published()
        → invalida HbosBundleCache (por CPF afetado ou globalmente)
        → aciona eager_reload_fn, se configurado (reload eager) — ou deixa o
          próximo acesso recarregar sob demanda (reload lazy, implícito)
        → InstanceModelVersionTracker.report()  (model_version_active por instância)
  → ModelRegistry.rollback()            (retorna à versão anterior; marca ROLLED_BACK)
```

Módulos: `src/antifraud/models_ml/registry.py`, `src/antifraud/models_ml/cache.py`.

Estados suportados no `ModelRegistry`: `candidate`, `challenger`, `champion`, `deprecated`,
`rolled_back` (`ModelRegistryState`), alinhados à seção "Estratégia de rollout e promoção de
modelos" do contexto operacional.

## O que este repositório NÃO implementa (fora de escopo)

- Cache distribuído real (Redis, etc.) — apenas a interface `HbosBundleCache` e uma
  implementação em memória.
- Dashboard de convergência — `InstanceModelVersionTracker` calcula `convergence_ratio` e
  `stale_instances`, mas não há visualização.
- Validação de integridade de artefato e compatibilidade de schema de features na publicação —
  `ModelRegistryEntry.feature_schema_hash` é um campo preparado para isso, mas a validação de
  hash/schema em si não está implementada.
- Qualquer pipeline de treino real.

## Critérios de aceite

- **100% das publicações de modelo aplicadas sem restart manual** →
  `tests/test_model_cache_invalidation.py::test_model_published_event_invalidates_specific_cpf`
  e `test_model_published_event_global_invalidation_when_no_cpfs_listed` comprovam que a
  invalidação ocorre via evento, sem qualquer reinício de processo.
- **Toda inferência registra a versão de modelo usada** → `ModelScore.model_version` é
  preenchido pelo `HbosScorer`/`XgboostScorer` e propagado ao `DecisionTrace` e ao
  `ChallengeEvent.model_versions` (ver `tests/test_cascade_short_circuit.py::test_decision_trace_always_records_scores_and_versions`).
- **Instâncias defasadas identificadas e alertadas** →
  `tests/test_model_cache_invalidation.py::test_instance_tracker_reports_active_version_after_publish`
  (o "alerta" em si, via canal de notificação, é um ponto de extensão fora de escopo).
- **Rollback rápido para a versão anterior** →
  `tests/test_model_cache_invalidation.py::test_model_registry_register_promote_and_rollback`.
- **Validação de integridade/compatibilidade de schema na publicação**: lacuna aberta,
  documentada acima.
