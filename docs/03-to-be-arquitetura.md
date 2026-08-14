# 03 — TO-BE: arquitetura alvo

A arquitetura alvo separa **hot path síncrono** (autorização) de **trilha
assíncrona** (challenge) e de **ciclo de modelos** (offline). AutoML e agentes
permanecem fora do caminho de autorização.

## Decisão de desenho

1. Unificar as três visões AS-IS em uma cascata explícita, com a Regra 83 como
   **hard rule nomeada e auditável**, não como pré-filtro silencioso.
2. Preservar short-circuit de hard rules críticas para latência e contenção.
3. Tratar HBOS como **sinal**, XGBoost como **score supervisionado**, regras
   como **política determinística**.
4. Publicar contexto rico em evento interno; HTTP v1 continua mínima.
5. Operacionalizar `challenge` antes de expandir agentes de IA.

## Visão de componentes

```text
[Autorizador / autenticador]
        │  HTTP v1: { decision_final }
        ▼
┌───────────────────────────────────────────┐
│  Motor de score (hot path, p95 < 100 ms)  │
│  validação → features → hard rules        │
│  → HBOS (sinal) → XGBoost (score)         │
│  → consolidação approve/challenge/deny    │
│  → auditoria + outbox                     │
└───────────────────────────────────────────┘
        │
        ├── approve/deny → resposta síncrona
        │
        └── challenge → evento fraud.challenge.created
                         │
                         ▼
              [fila de triagem + persistência]
                         │
                         ▼
              [workflow de validadores — planejado]
                         │
                         ▼
              approve / deny / escalate → notificação + auditoria

[ciclo MLOps offline]
  dados maduros → treino (HBOS/XGBoost/AutoML) → registry
  → shadow → canário → model.published → reload de cache
```

## Cascata online TO-BE

Ordem executada no hot path, com possibilidade de encerrar cedo:

| # | Camada | Pode encerrar? | Decisões típicas |
| --- | --- | --- | --- |
| 1 | Receber transação + `correlation_id` | Não | Inicia trace/auditoria |
| 2 | Validar payload | Sim | Erro controlado / rejeitar |
| 3 | Calcular features | Sim (cobertura crítica) | Fallback seguro documentado |
| 4 | Hard rules (inclui Regra 83, blocklist, valor, viagem impossível) | Sim se regra crítica | `deny` imediato ou sinal |
| 5 | Política de cold start | Sim | `approve` monitorado, `challenge`, `deny`/`escalate` |
| 6 | HBOS individual | Não como prova; pode short-circuit só se política exigir | Sinal de anomalia |
| 7 | XGBoost global | Não isoladamente | Score supervisionado |
| 8 | Consolidação por faixas configuráveis | Sim | `approve` / `challenge` / `deny` |

A Regra 83 **não** aprova o restante do universo de forma invisível: transações
fora da regra seguem para consolidação com reason code `rule_83_not_triggered`
e podem ainda ser negadas/desafidas por hard rule crítica, cold start, HBOS ou
XGBoost. Uma amostra configurável (1–5%) avalia **todas** as camadas em shadow,
sem afetar a decisão online.

WhatsApp de confirmação deixa de ser o significado de “caiu na 83”. Passa a ser
**um** step-up possível da trilha de challenge, ao lado de outros validadores.

## Fronteiras de latência

| Caminho | SLA | Permitido | Proibido |
| --- | --- | --- | --- |
| Fast path approve/deny | p95 < 100 ms | Inferência local em cache, regras, features pré-computáveis | AutoML remoto, bureau, WhatsApp, agentes |
| Challenge assíncrono | segundos a minutos, com timeout por validador | Fila, workflow, step-up, bureau, geo/device | Bloquear a autorização HTTP |
| Treino / AutoML | offline, horas/dias | AML, notebooks, registry | Qualquer chamada na transação |

## Publicação de decisão

| Canal | Conteúdo | Consumidor |
| --- | --- | --- |
| HTTP v1 | `decision_final` | Autorizador atual |
| HTTP v2 (autorizada) | score, signals, features, pesos, reason codes, versões | Consumidores de explicabilidade |
| Evento interno | contexto completo de challenge | Orquestrador / fila |
| Log estruturado / auditoria | camadas, versões, fallback | SIEM, LGPD, contestação |

## Relação com o autenticador

O autenticador (saldo, senha, cartão) permanece **antes** do motor. Falha de
autenticação não entra no score: é `compra negada` de domínio de autorização,
não `deny` antifraude. O motor só recebe transação autenticada.

## O que permanece fora desta entrega de código

Este repositório entrega contratos, política simulada e critérios de aceite.
Não implanta Agent Framework, Azure AutoML, WhatsApp, bureau nem o microserviço
real. Essas peças entram no roadmap em [10](10-roadmap-criterios-aceite.md).
