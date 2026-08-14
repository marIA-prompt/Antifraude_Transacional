# 06 — Publicação de modelos e invalidação de cache

Prioridade 2.

## AS-IS

HBOS e XGBoost são servidos via cache em memória (bundles por CPF no HBOS,
artefato global no XGBoost). Retreino pode exigir restart ou limpeza manual.

## Lacuna / risco

Instâncias defasadas, rollback lento, inferência sem `model_version` auditável.

## TO-BE

```text
Pipeline de treino (offline)
→ valida artefato (hash, schema de features, tamanho, smoke inference)
→ registra versão no model registry
   estados: candidate | challenger | champion | deprecated | rolled_back
→ publica bundle atômico
→ promove
→ emite model.published
→ invalida cache distribuído
→ reload lazy ou eager por instância
→ registra model_version_active
→ dashboard de convergência
```

Schema: [`contracts/events/model.published.schema.json`](../contracts/events/model.published.schema.json)

Regras:

- publicação nunca ocorre no hot path da transação;
- reload não pode bloquear p95: double-buffer (carrega novo, troca ponteiro);
- rollback aponta o ponteiro para a versão `rolled_back` anterior já residente
  ou a rebaixa do registry em segundos;
- instância que não convergiu em T segundos gera alerta;
- HBOS por CPF: invalidação seletiva por `subject_id` ou por geração do bundle.

## Critérios de aceite

- 100% das publicações aplicadas sem restart manual.
- Toda inferência registra versão usada (HBOS e XGBoost).
- Instâncias defasadas identificadas e alertadas.
- Rollback para versão anterior validado em teste.
- Schema de features incompatível rejeita a publicação.
- Testes: `tests/test_model_cache.py`.
