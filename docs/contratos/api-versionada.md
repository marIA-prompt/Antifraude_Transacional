# Contrato da API: v1 preservada, v2 com explicabilidade

Especificação normativa: [`contracts/openapi/score-api.yaml`](../../contracts/openapi/score-api.yaml)

Endpoint AS-IS do briefing: `POST /api/v1/score-transaction`.

## AS-IS — divergência D-1

| Fonte | Saída |
|---|---|
| Especificação do microserviço | `score`, `decision`, `signals`, `features`, `feature_weights` |
| Implementação | `{ "decision_final": "approve \| challenge \| deny" }` |

Limitação registrada: *"Resposta HTTP só com `decision_final` → integrador não vê
score/sinais. Detalhe está no log."*

Validação AS-IS do payload: CPF 11 dígitos, CNPJ 14, valores positivos, tipos (Pydantic).
Os contratos deste repositório **não** aceitam campo `cpf` — o TO-BE de entrada é
`subject_token` / identificador tokenizado ([LGPD](../governanca/lgpd-e-dados-sensiveis.md)).

## Lacuna/Risco

Consumidores autorizados (analistas, painel de disputas) não têm caminho suportado, o que
pressiona dois anti-padrões: ler o banco de auditoria ou acoplar orquestração à HTTP do
autorizador. Devolver tudo na v1 quebra integradores e expõe a lógica antifraude.

## TO-BE

```text
API v1: mantém decision_final; retrocompatível; não quebra integrações.
API v2: score, decision, signals, features, feature_weights, reason codes,
        model_versions — com autenticação, autorização por perfil,
        mascaramento e proteção contra exposição da lógica antifraude.
```

**A v1 não evolui.** Qualquer necessidade nova entra na v2 (`POST /api/v2/score-transaction`).

**A v2 filtra por perfil:**

| Campo | Perfil operacional | Perfil de análise antifraude |
|---|---|---|
| `decision`, `score`, `reason_codes` | sim | sim |
| `signals` | não | sim |
| `features`, `feature_weights` | não | sim, com mascaramento |
| `model_versions` | não | sim, quando permitido |
| `cohort` | sim | sim |

`reason_codes` sempre presente: insumo mínimo para atendimento e revisão de decisão
automatizada (art. 20). Códigos inteligíveis, não opacos.

**A orquestração de challenge não consome nenhuma das duas APIs.** Contexto pelo evento
[`fraud.challenge.created`](evento-challenge.md).

Idempotência: `X-Idempotency-Key` devolve a decisão original, sem recalcular — a v2 não vira
oráculo para sondar o modelo.

Rate limiting específico da v2: consultas repetidas variando um parâmetro mapeiam
thresholds. Auditar padrão de uso, não só volume.

## Critérios de aceite

- Testes de contrato: v1 byte-compatível, somente `decision_final`,
  `additionalProperties: false`.
- Nenhum consumidor da v1 alterado no rollout da v2.
- Perfil sem escopo: `403`. Perfil parcial: campos restritos ausentes.
- Nenhuma resposta com CPF em claro, verificado por teste.
- Latência da v1 não afetada pela existência da v2, medida em carga (p95 da v1 permanece
  no orçamento de [100 ms](../arquitetura/orcamento-de-latencia.md)).
- Acesso à v2 em trilha de auditoria consultável.
- Nenhum componente de orquestração referencia as APIs de score (revisão de dependências).
