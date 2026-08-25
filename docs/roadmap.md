# Roadmap de execução

Fases por **dependência técnica**, sem estimativa de calendário. Regra: **instrumentar
antes de mudar decisão, e operacionalizar desfecho antes de gerar mais casos.**

Prioridade do briefing: `challenge` → invalidação de cache → cold start → só então agentes
de IA. AutoML permanece offline.

O MAPA ([acompanhamento-modelagem.md](mlops/acompanhamento-modelagem.md)) corre em paralelo
como protocolo de modelagem e **não fecha modelo novo antes da Etapa 1**.

## Fase 0 — Telemetria, shadow e conciliação documental

Escopo: campos do decision trace; shadow 1%–5%; dashboards de latência por etapa, fallback
e divergência HBOS/XGB; auditoria de features (D-2); diagnóstico NEG83 × score (D-3, MAPA
Etapa 1).

**Saída que destrava o resto:** `short_circuit_layer` em 100% das transações; registry de
features em andamento; D-3 com evidência ou explicitamente "sistemas paralelos".

## Fase 1 — Operacionalizar o `challenge`

**Depende de:** Fase 0 (medir o efeito).

1. evento `fraud.challenge.created`;
2. persistência de contexto;
3. fila de triagem;
4. regras adicionais;
5. step-up (WhatsApp só depois de D-3, como validador desacoplado);
6. fila humana para `escalate`;
7. notificação idempotente;
8. integrações externas (bureau, blocklist, geo, device) **somente aqui**;
9. agentes de IA — **somente após** controles determinísticos.

**Critério de saída:** 100% dos `challenge` com desfecho; SLOs da
[trilha](workflows/trilha-de-challenge.md) (p95 workflow, timeouts 800 ms / 2 s, fallback
< 1%, mediana step-up < 5 min, backlog < 30 min, escalate 24 h = 0%).

## Fase 2 — Publicação de modelos e invalidação de cache

**Depende de:** Fase 0 (`model_version` por inferência).

[ADR-0004](adr/0004-publicacao-de-modelos-e-cache.md): publicação atômica, evento,
invalidação `cpf_token + model_version`, convergência < 5 min, rollback < 10 min, 100% sem
restart.

## Fase 3 — API v2 com explicabilidade

**Depende de:** Fase 0. Pode correr em paralelo a 1 e 2. Não altera decisão.

[API versionada](contratos/api-versionada.md). v1 congelada em `decision_final`.

## Fase 4 — Política de cold start

**Depende de:** Fase 1 (challenge com desfecho) e Fase 2 (pesos/configuração publicáveis).

[ADR-0003](adr/0003-politica-de-cold-start.md): faixas `X`/`Y`, peso HBOS 0, reason code
`cold_start`, coorte separada. Modelo dedicado de cold start só após MAPA Etapas 1–6.

## Fase 5 — Calibração, challengers e AutoML offline

**Depende de:** Fases 0 e 2, e das Etapas 1–4 do MAPA.

Shadow ≥ 4 semanas; `average_precision_score_weighted`; `blocked_models` se p95 > 15 ms;
promoção champion/challenger; rollback < 10 min. Motor H, se aprovado, segue teste
assistido **fora** desta cascata ([motor-h-neg83.md](recuperacao/motor-h-neg83.md)).

Mudança de topologia (avaliação paralela, HBOS nunca terminal) **não é fase**. Reabre só
com números da amostra shadow, conforme [ADR-0001](adr/0001-topologia-de-decisao.md).

## Resumo de dependências

```text
Fase 0 (telemetria + shadow + D-2/D-3)
  ├── Fase 1 (challenge operacional)
  │     └── Fase 4 (cold start)
  ├── Fase 2 (publicação de modelos)
  │     ├── Fase 4
  │     └── Fase 5 (calibração + challengers offline)
  └── Fase 3 (API v2)  [não altera decisão]
```

Diagrama: [mapa mental](mapa-mental.md).

## Riscos transversais

| Risco | Mitigação | Limiar |
|---|---|---|
| Fase 4 aumenta challenge sem fila | Fase 1 obrigatória antes | 100% desfecho |
| Rótulos imaturos inflam Fase 5 | janela de maturação; `sem_desfecho` fora da negativa | teste de pipeline |
| Cache miss estoura p95 | timeout 20 ms; `hbos_unavailable` | p95 < 100 ms |
| AutoML ou bureau no hot path | teste de tracing; blocked_models 15 ms | 0 chamadas no span |
| Agentes antes dos controles | item 9 da Fase 1 | — |
| Evento de publicação perdido | reconciliação contra registry | convergência < 5 min |
| Afirmar 10 ou 13 features | registry `unreconciled` | critério 11 |
