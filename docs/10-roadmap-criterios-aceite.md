# 10 — Roadmap e critérios de aceite

Agentes e AutoML não são pré-requisito das três prioridades. Nada abaixo
afirma que já está em produção.

## Ordem

```text
P0.1  Evento + outbox + persistência de challenge
P0.2  Fila de triagem + desfecho rastreável
P0.3  Publicação de modelo + invalidação de cache
P0.4  Política de cold start configurável
P1.1  API v2 autenticada
P1.2  Envelope de auditoria + shadow 1–5%
P1.3  Unificação da Regra 83 (hard rule auditável)
P1.4  Step-up (WhatsApp) desacoplado da Regra 83
P2.1  Validadores determinísticos (bureau/geo/device)
P2.2  Fila humana de escalate
P2.3  Pipeline de rótulos maduros + drift
P3.1  AutoML offline champion/challenger
P3.2  Agent Framework Workflows na trilha de challenge
```

## Rollout de qualquer mudança de política ou modelo

```text
Dados validados
→ treino/config offline
→ validação temporal (quando ML)
→ performance, custo e viés
→ registry / config versionada
→ shadow
→ canário
→ monitoramento
→ champion ou rollback
```

Canário de política: percentual de transações na nova consolidação; o restante
permanece na política vigente. O autorizador não muda.

## Matriz de aceite consolidada

| ID | Critério | Como provar |
| --- | --- | --- |
| C1 | HTTP v1 só `decision_final` | `tests/test_api_contracts.py` |
| C2 | v2 recusa sem autorização e mascara sujeito | contrato OpenAPI + testes |
| C3 | 100% challenge emite evento idempotente | `tests/test_challenge_outbox.py` |
| C4 | Challenge não chama AutoML nem agente | inspeção do hot path no simulador |
| C5 | Toda inferência registra versão de modelo | `tests/test_model_cache.py` |
| C6 | Publicação troca ponteiro sem restart | `tests/test_model_cache.py` |
| C7 | Rollback restaura champion anterior | `tests/test_model_cache.py` |
| C8 | CPF novo: HBOS peso 0 + reason `cold_start` | `tests/test_cold_start.py` |
| C9 | Alto valor + CPF novo não aprova por omissão | `tests/test_cold_start.py` |
| C10 | Hard rule crítica prevalece sobre scores | `tests/test_decision_cascade.py` |
| C11 | HBOS sozinho não gera `deny` | `tests/test_decision_cascade.py` |
| C12 | Envelope registra camadas executadas/puladas | `tests/test_observability.py` |
| C13 | Shadow não altera decisão | `tests/test_observability.py` |
| C14 | Eventos sem campo CPF | `tests/test_lgpd_schemas.py` |
| C15 | p95 do fast path sem I/O de challenge | simulador: publisher é outbox in-memory pós-decisão |

Critérios de produto (não automatizados neste repo): RIPD, dashboard de
convergência de cache, SLA de desfecho de challenge, calibração de thresholds
com dados reais Senff.

## Fora de escopo deste repositório

- Código do microserviço de produção.
- Integração WhatsApp, bureau, geo, device.
- Conta Azure ML / Agent Framework.
- Treino real de HBOS/XGBoost.
