# 04 — Contratos de API

## AS-IS

A apresentação mais recente indica que a resposta HTTP expõe:

```json
{ "decision_final": "approve | challenge | deny" }
```

A especificação original previa `score`, `decision`, `signals`, `features` e
`feature_weights`.

## Lacuna / risco

Consumidores e o futuro orquestrador de challenge não podem depender da v1
para explicabilidade. Ampliar a v1 sem versionamento quebra clientes ou vaza
lógica.

## TO-BE

Arquivos canônicos:

- [`contracts/openapi/v1.yaml`](../contracts/openapi/v1.yaml)
- [`contracts/openapi/v2.yaml`](../contracts/openapi/v2.yaml)

### API v1 — autorizador

| Campo | Obrigatório | Notas |
| --- | --- | --- |
| `decision_final` | sim | `approve`, `challenge`, `deny` |

Erros de payload usam HTTP 4xx com reason code controlado, sem stack trace.

`challenge` na v1 significa: a transação **não** foi aprovada nem negada no
hot path; o desfecho operacional virá da trilha assíncrona. O autorizador deve
tratar `challenge` segundo o contrato de produto vigente (hoje: passo equivalente
ao disparo de confirmação; amanhã: pending/step-up). Esse contrato de produto
é independe do payload rico.

### API v2 — explicabilidade (consumidores autorizados)

Campos:

- `score` consolidado 0–1
- `decision`
- `signals[]`
- `features` (mascarados / minimizados)
- `feature_weights` (escopo separado)
- `reason_codes[]`
- `model_versions` (quando o perfil permitir)
- `layers_executed` / `layers_skipped` / `terminated_by`
- `correlation_id`

Controles:

- autenticação mTLS ou JWT de serviço;
- autorização por perfil (`score:read`, `explain:features`, `explain:weights`);
- mascaramento de CPF (token ou hash truncado);
- recusa de devolver regras internas textuais completas;
- audit log de quem consultou a v2.

## Critérios de aceite

- Cliente v1 existente continua válido sem alteração.
- v2 recusa request sem escopo adequado (401/403).
- CPF nunca aparece em claro na v2.
- Nenhuma resposta v1 inclui `features` ou `feature_weights`.
- Testes de contrato em `tests/test_api_contracts.py`.
