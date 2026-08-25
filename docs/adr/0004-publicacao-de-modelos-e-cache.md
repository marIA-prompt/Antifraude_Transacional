# ADR-0004 — Publicação de modelos e invalidação de cache

- **Status:** aceito (revisado em 2026-08-25)
- **Lacuna endereçada:** L2 (cache exige restart ou limpeza manual após retreino)
- **Depende de:** schema de features versionado — enquanto D-2 estiver aberto, a validação
  de compatibilidade compara contra a versão *em uso na instância*, não contra uma lista
  canônica 10/13

## Contexto

### AS-IS

Bundles de HBOS (modelo, scaler, perfis) e o XGBoost global são servidos a partir de cache
em memória. Isso é a razão da latência baixa (budget de 8 ms no hit) e não deve mudar.
Treino noturno + fila já existem.

### Lacuna/Risco

Depois de um retreinamento, o serviço pode continuar usando versões antigas em cache,
exigindo restart ou limpeza manual:

1. **Defasagem silenciosa** — a mesma transação teria decisões distintas por pod.
2. **Análise post-mortem inválida** — sem `model_version` por inferência.
3. **Rollback lento** — intervenção manual no momento em que o tempo importa.

## Decisão

Pipeline do briefing:

```text
Pipeline de treino
→ valida integridade do artefato e compatibilidade de schema de features
→ registra versão no model registry
→ publica bundle de forma atômica
→ promove versão
→ emite evento model.published
→ invalida cache distribuído (chave: cpf + model_version)
→ reload lazy (próxima requisição) ou eager (warm-up)
→ registra model_version_active por instância
→ dashboard confirma convergência entre réplicas
```

**Publicação atômica:** escrita em caminho novo e imutável + troca de ponteiro. Nenhuma
instância observa bundle parcialmente escrito.

**Invalidação em duas camadas.** `model.published` invalida a chave no cache distribuído e
sinaliza reload do cache local. Enquanto a nova versão não estiver carregada e validada, a
instância **continua servindo a anterior**. Degradar para "sem modelo" no fast path não é
aceitável; o fallback é o da [escada](../arquitetura/orcamento-de-latencia.md).

**Granularidade do HBOS.** Muitos artefatos pequenos, cadência por CPF. Invalidação global a
cada retreino individual provocaria tempestade de recarga. Chave: `cpf_token + model_version`
(CPF nunca em claro na chave de cache de evento/log). Evento de publicação do HBOS carrega
o conjunto de identificadores afetados.

**Estados no registry:** `candidate` → `challenger` → `champion` → `deprecated` |
`rolled_back`. `rolled_back` bloqueia repromoção acidental da mesma versão.

**Rollback:** troca de ponteiro, acionável por configuração, sem deploy, **< 10 min**.

**Reconciliação:** a instância compara `model_version_active` com a versão promovida no
registry em ciclo periódico, independentemente do evento — evento perdido não é modo de
falha silencioso.

**Compatibilidade de schema:** promoção falha se o artefato não declarar
`feature_schema_version` compatível com o servido. Enquanto o registry de features estiver
`unreconciled`, a comparação é de hash/versão opaca, não de cardinalidade 10 vs 13.

## Critérios de aceite

- **100%** das publicações aplicadas sem restart manual.
- Convergência de versão entre réplicas **< 5 min** (p95), visível em dashboard.
- **100%** das inferências com `model_version` registrada (bundle HBOS e/ou XGBoost).
- Rollback para a versão anterior **< 10 min**, exercitado em teste com tempo medido.
- Alerta automático de instância defasada acima do limite configurado.
- Publicação falha, sem promover, quando integridade, schema de features ou carregabilidade
  não passam.
- Reconciliação periódica detecta divergência mesmo com perda de `model.published`.
- Nenhuma instância serve decisão sem modelo carregado: falha de carga mantém a versão
  anterior e emite alerta.
