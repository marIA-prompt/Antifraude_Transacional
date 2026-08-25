# Orçamento de latência e escada de degradação

Restrição estruturante do briefing: **p95 do fast path < 100 ms**. Não é meta aspiracional —
é hard deadline de autorização.

## AS-IS

A cascata com short-circuit existe precisamente para caber neste orçamento: `HBOS = deny`
economiza os 15 ms do XGBoost. Bundle HBOS é servido em cache de memória sobre PostgreSQL.
Validação de payload é Pydantic.

O briefing reserva **0 ms** no caminho síncrono para persistência de log/auditoria
(fire-and-forget). Se a implementação atual persiste log de forma síncrona, isso é
[`L9`](00-contexto-as-is.md).

## TO-BE: orçamento por etapa (p95)

| Etapa | Budget p95 | Observação |
|---|---|---|
| Validação de payload | 5 ms | Pydantic |
| Carga do bundle (cache **hit**) | 8 ms | Memória |
| Cálculo de features | 25 ms | Maior consumidor — alvo de otimização |
| HBOS + regras + hard-rule | 12 ms | Determinístico |
| XGBoost global (quando executa) | 15 ms | Não executa se HBOS = deny |
| Consolidação dual | 5 ms | Média ponderada |
| Rede + serialização | 15 ms | — |
| Buffer de variação | 15 ms | Absorve picos |
| **Total** | **100 ms** | **Hard deadline** |
| Persistência de log/auditoria | **0 ms** | **Assíncrono, fire-and-forget** |

Alerta de latência: p95 de qualquer etapa acima de 80% do seu budget, ou p95 total ≥ 90 ms.

Modelos cujo p95 de inferência exceda **15 ms** entram em `blocked_models` da esteira
offline de AutoML — não são candidatos ao hot path.

## TO-BE: escada de degradação

```text
Cache MISS do bundle HBOS:
→ tentar carregar do PostgreSQL com timeout de 20 ms
→ se exceder: decidir com XGBoost global + regras + hard rules
→ reason code: hbos_unavailable
→ disparar warm-up assíncrono do bundle
→ NUNCA estourar o deadline aguardando I/O de modelo

Falha do XGBoost:
→ manter decisão do HBOS + regras (fail-safe da cascata, já existente)
→ reason code: xgb_unavailable

Falha de dependência externa no fast path:
→ proibido no caminho síncrono; validadores externos vivem só no challenge
```

| Camada | Falha | Comportamento | Reason code | Registro |
|---|---|---|---|---|
| Bundle HBOS, cache miss | I/O PostgreSQL | timeout **20 ms**; segue com XGBoost + regras + hard rules | `hbos_unavailable` | `fallback_reason`, `score_hbos = null` |
| XGBoost | erro/timeout | mantém HBOS + regras | `xgb_unavailable` | `score_xgb = null` |
| Dependência externa (bureau, device, geo enriquecida) | qualquer | **não entra no fast path** | — | só na trilha de challenge, timeout 800 ms interno / 2 s externo |
| Cache de publicação | evento perdido | reconciliação periódica contra o registry; mantém versão local | instância defasada | alerta se convergência > 5 min |

Score de camada não executada ou indisponível é **`null`**, nunca `0`. Zero seria lido como
"o modelo não acusou risco".

## Lacuna/Risco

- Esperar I/O de modelo além de 20 ms no miss viola o hard deadline.
- Fallback silencioso (sem reason code) impede distinguir degradação de decisão plena.
- Validadores externos no caminho síncrono destroem o SLA mesmo com taxa de erro baixa: um
  p95 de bureau de 2 s é vinte vezes o orçamento total.

## Critérios de aceite

- p95 do fast path < 100 ms, medido em carga de pico, com histograma por etapa.
- 100% dos cache miss de bundle com timeout ≤ 20 ms no caminho síncrono.
- 100% das decisões em fallback com `fallback_reason` ∈ {`hbos_unavailable`,
  `xgb_unavailable`} (ou extensão catalogada).
- Taxa de fallback por camada visível em dashboard, com alerta acima do limite configurado.
- Zero chamadas de rede a bureau, AutoML, LLM ou device intelligence no span da autorização
  — verificado por teste de contrato / tracing.
- Persistência de log com p95 de acréscimo ao fast path < 1 ms (fila local; perda de log
  visível como métrica, nunca como bloqueio).
