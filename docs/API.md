# Contrato de API — v1 e v2

## AS-IS: divergência de contrato

- A especificação original previa `score`, `decision`, `signals`, `features` e `feature_weights`.
- A implementação AS-IS mais recente (relatada na apresentação de referência) expõe apenas
  `decision_final` na resposta HTTP. Score, sinais, features e pesos ficam em logs/eventos internos.
- **Este repositório assume que a API HTTP pode expor somente `decision_final`** (diretriz
  obrigatória do contexto operacional) e modela a v1 dessa forma deliberadamente
  (`src/antifraud/api/v1.py`).

## TO-BE: contrato versionado implementado neste repositório

### API v1 — `POST /v1/transactions/authorize`

Retrocompatível. Resposta:

```json
{ "decision_final": "approve | challenge | deny | escalate | reject" }
```

Implementação: `src/antifraud/api/v1.py`. Nenhum dado de explicabilidade é exposto aqui.

### API v2 — `POST /v2/transactions/authorize`

Requer autenticação via header `X-API-Key` e autorização por perfil
(`src/antifraud/api/deps.py`, `ApiConsumerRole`: `basic`, `analyst`, `admin`).

```json
{
  "transaction_id": "...",
  "correlation_id": "...",
  "score": 0.42,
  "decision": "challenge",
  "signals": [...],
  "features": {...},
  "feature_weights": {...},
  "reason_codes": [...],
  "rule_evidences": [...],
  "model_versions": {...},
  "executed_layers": [...],
  "terminating_layer": "hard_rules",
  "is_cold_start": false,
  "is_shadow_sample": false
}
```

- Perfil `basic`: recebe o payload com `features`, `feature_weights`, `model_versions` e
  `rule_evidences` mascarados (vazios), para reduzir exposição indevida da lógica antifraude.
- Perfis `analyst`/`admin`: recebem o payload completo.
- Sem header válido: `401 Unauthorized`.

**Importante**: o orquestrador de `challenge` (ver `CHALLENGE_WORKFLOW.md`) **não depende**
desta resposta HTTP v1. Ele consome o `DecisionTrace` diretamente via
`AntifraudService.decide` → `ChallengeOperationsService.handle_challenge_decision`, que monta
e publica o evento `fraud.challenge.created` internamente.

## Lacuna/Risco em aberto (fora de escopo deste stub)

- A autenticação da v2 aqui é uma tabela em memória (`_DEMO_API_KEYS`) apenas para
  demonstração — produção deve usar um provedor de identidade real (OAuth2/mTLS) e
  autorização centralizada.
- Mascaramento de dados sensíveis (CPF etc.) não é aplicável na resposta v2 atual porque o
  `DecisionTrace` já não carrega CPF em claro (é descartado após a tokenização na fronteira do
  motor); qualquer novo campo que inclua PII deve passar por mascaramento explícito antes de
  ser adicionado ao contrato v2.

## Critério de aceite

- Testes de contrato (`tests/test_api_v1_v2_contract.py`) garantem que:
  - a resposta v1 contém exclusivamente a chave `decision_final`;
  - a v2 sem autenticação retorna `401`;
  - a v2 com perfil `analyst`/`admin` retorna `features`/`feature_weights`/`model_versions`
    não vazios quando aplicável;
  - a v2 com perfil `basic` retorna esses mesmos campos mascarados;
  - v1 e v2, para o mesmo cenário de risco, concordam na decisão subjacente.
