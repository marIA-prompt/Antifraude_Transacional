# Contrato da API: v1 preservada, v2 com explicabilidade

Especificação normativa: [`contracts/openapi/score-api.yaml`](../../contracts/openapi/score-api.yaml)

## Divergência AS-IS

A documentação original do microserviço previa cinco saídas estruturadas:

```json
{ "score": 0.0, "decision": "approve | challenge | deny", "signals": [], "features": {}, "feature_weights": {} }
```

A implementação atual expõe apenas:

```json
{ "decision_final": "approve | challenge | deny" }
```

Score, sinais, features e pesos permanecem em logs e eventos internos.

### Lacuna/Risco

Consumidores autorizados que precisam de explicabilidade (analistas, painel de disputas,
orquestração de triagem) não têm caminho suportado, o que cria pressão por dois anti-padrões:
ler o banco de auditoria diretamente, ou acoplar orquestração à resposta HTTP do autorizador.

O caminho oposto — simplesmente devolver tudo na v1 — é igualmente ruim: quebra os
autorizadores existentes e expõe a lógica antifraude a consumidores que não deveriam
inspecioná-la, o que é um risco de engenharia reversa da política de risco por quem tem acesso à
API.

## Decisão

**A v1 não evolui.** Continua expondo `decision_final` e permanece o contrato dos autorizadores
existentes. Qualquer necessidade nova entra na v2.

**A v2 expõe explicabilidade sob controle de acesso.** Requer autenticação, escopo dedicado
(`antifraude.score.explain`) e autorização por perfil. O nível de detalhe é **filtrado pelo
perfil do consumidor**:

| Campo | Perfil operacional | Perfil de análise antifraude |
|---|---|---|
| `decision`, `score`, `reason_codes` | sim | sim |
| `signals` | não | sim |
| `features`, `feature_weights` | não | sim, com mascaramento |
| `model_versions` | não | sim, quando permitido |
| `cohort` | sim | sim |

`reason_codes` está sempre presente, porque é o insumo mínimo para atendimento ao cliente e para
pedido de revisão de decisão automatizada (art. 20 da LGPD). Os códigos precisam ser
inteligíveis, não identificadores internos opacos.

**A orquestração de challenge não consome nenhuma das duas APIs.** Ela recebe contexto pelo
evento [`fraud.challenge.created`](evento-challenge.md). Essa separação é o que permite manter a
v1 intacta e o fast path livre do custo da orquestração.

## Considerações de segurança e privacidade

- `subject_token` no lugar de CPF em claro, na requisição e na resposta.
- Mascaramento de campos sensíveis em `features` e em evidências, aplicado no servidor — nunca
  delegado ao cliente.
- Rate limiting específico da v2: consultas repetidas variando um parâmetro por vez permitem
  mapear thresholds. O padrão de uso deve ser monitorado, e não apenas o volume.
- Trilha de auditoria de acesso à v2: quem consultou qual transação e qual nível de detalhe
  recebeu.
- Ausência de reavaliação em consulta idempotente: `X-Idempotency-Key` retorna a decisão
  original em vez de recalcular, evitando que a v2 se torne um oráculo para sondar o modelo com
  variações de payload.

## Critérios de aceite

- Testes de contrato garantindo que a resposta da v1 permanece byte-compatível com o AS-IS.
- Nenhum consumidor da v1 precisa de alteração para o rollout da v2.
- Perfil sem escopo recebe `403`, e perfil com escopo parcial recebe resposta sem os campos
  restritos — verificado por teste automatizado por perfil.
- Nenhuma resposta contém CPF em claro nem campo sensível sem mascaramento, verificado por teste
  automatizado.
- Latência da v1 não é afetada pela existência da v2, medida em carga.
- Acesso à v2 registrado em trilha de auditoria consultável.
- Nenhum componente de orquestração de challenge referencia as APIs de score, verificado por
  revisão de dependências.
