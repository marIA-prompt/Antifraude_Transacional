# Contrato do evento `fraud.challenge.created`

Schema normativo: [`contracts/events/fraud.challenge.created.schema.json`](../../contracts/events/fraud.challenge.created.schema.json)

## Por que existe

### Lacuna/Risco

A banda `challenge` existe na lógica de decisão, mas não possui fluxo operacional completo. Uma
transação pode ser classificada como questionável sem acionar fila, step-up, análise humana,
validação adicional ou notificação. E como a API v1 expõe apenas `decision_final`, um
orquestrador que dependesse da resposta HTTP não teria score, sinais, features nem versões de
modelo para trabalhar.

### TO-BE

O orquestrador de challenge **não depende da resposta HTTP**. Ele recebe todo o contexto por
este evento interno, publicado de forma assíncrona pelo serviço de autorização. Isso mantém a
API v1 retrocompatível e o fast path livre do custo da orquestração.

```text
ML + regras → challenge
→ evento fraud.challenge.created
→ fila de triagem
→ workflow de validadores
→ decisão consolidada: approve / deny / escalate
→ notificação sim/não
→ auditoria
```

## Dados mínimos transportados

O schema cobre o conjunto mínimo acordado: identificadores (`transaction_id`,
`correlation_id`, `subject_token`, `occurred_at`), escores (HBOS, modelo global, cold start,
consolidado calibrado), sinais e regras acionadas com evidência, features relevantes e pesos,
versões de todos os artefatos, rastro de execução (camadas executadas, não executadas, camada
que encerrou e camada que elevou o risco), decisão inicial e o contexto da transação necessário
aos validadores.

Três campos merecem destaque porque costumam ser esquecidos:

- **`scores.hbos_weight_applied`** — o peso efetivo do HBOS. Sem ele não é possível distinguir
  "HBOS não acusou nada" de "HBOS foi zerado por cold start".
- **`execution.risk_escalating_layer`** — a camada que elevou o risco pode ser diferente da que
  encerrou a decisão. Confundir as duas distorce a análise de causa.
- **`execution.shadow_mode`** — permite publicar avaliações de shadow no mesmo contrato sem
  contaminar a fila operacional, desde que o consumidor filtre por esse campo.

## Idempotência

`idempotency_key` é a combinação de `transaction_id` e `correlation_id`. Consumidores devem
tratar entregas repetidas como a mesma unidade de trabalho: a fila de triagem não cria dois
casos, o workflow não executa validadores duas vezes e a notificação não é enviada em
duplicidade. `event_id` identifica a entrega, não o caso — não use `event_id` como chave de
deduplicação.

## Privacidade e LGPD

- O titular é identificado por `subject_token` (identificador interno ou CPF tokenizado).
  **CPF em claro não trafega no evento.**
- `features`, `feature_weights` e `evidence` estão sujeitos a minimização: transportar apenas o
  que os validadores efetivamente consomem, com mascaramento de campos sensíveis.
- A retenção do tópico e do banco de auditoria deve ter prazo definido e justificado; a janela
  de ~730 dias do HBOS é finalidade de modelagem, não autorização automática para retenção
  irrestrita de evento operacional.
- Como o evento sustenta decisões automatizadas com efeito sobre o cliente, ele é a base
  probatória para pedido de revisão (art. 20 da LGPD). Reason codes precisam ser inteligíveis, e
  não apenas identificadores internos.

## Evolução do contrato

Versionamento semântico em `event_version`. Adição de campo opcional é mudança menor. Remoção,
renomeação ou alteração de significado de campo existente exige nova versão maior, com período
de publicação dupla até que todos os consumidores migrem. `additionalProperties: false` é
intencional: um produtor que envia campo desconhecido deve falhar a validação em vez de
introduzir dado não contratado no fluxo de auditoria.

## Exemplo

```json
{
  "event_name": "fraud.challenge.created",
  "event_version": "1.0.0",
  "event_id": "6f9619ff-8b86-d011-b42d-00cf4fc964ff",
  "occurred_at": "2026-08-14T18:22:31.412Z",
  "idempotency_key": "txn-9912834:corr-4471a",
  "transaction_id": "txn-9912834",
  "correlation_id": "corr-4471a",
  "subject_token": "sbj_7f3c1a9e",
  "decision_initial": "challenge",
  "scores": {
    "hbos": null,
    "hbos_weight_applied": 0,
    "global_model": null,
    "cold_start_model": 0.71,
    "consolidated": 0.63,
    "calibration_applied": true
  },
  "signals": [
    {
      "code": "cold_start",
      "source": "business_rule",
      "outcome": "triggered",
      "severity": "medium",
      "evidence": { "cohort": "sem_historico", "dias_relacionamento": 2 }
    },
    {
      "code": "regra_83",
      "source": "business_rule",
      "outcome": "triggered",
      "severity": "high",
      "evidence": { "valor_acima_do_limite_do_canal": true }
    },
    {
      "code": "merchant_novo_para_titular",
      "source": "business_rule",
      "outcome": "triggered",
      "severity": "low",
      "evidence": { "primeira_compra_no_estabelecimento": true }
    },
    {
      "code": "blocklist_device",
      "source": "blocklist",
      "outcome": "not_triggered",
      "severity": "info",
      "evidence": {}
    }
  ],
  "features": {
    "valor_normalizado_canal": 0.82,
    "transacoes_ultimas_24h": 3,
    "device_compartilhado_por_n_titulares": 1,
    "distancia_km_ultima_transacao": 12.4
  },
  "feature_weights": {
    "valor_normalizado_canal": 0.31,
    "transacoes_ultimas_24h": 0.12,
    "distancia_km_ultima_transacao": 0.05
  },
  "model_versions": {
    "hbos_bundle_version": null,
    "global_model_version": null,
    "cold_start_model_version": "cold_start_gbdt:2026.08.02",
    "calibration_version": "isotonic_cold_start:2026.08.02",
    "rules_version": "rules:2026.07.28",
    "policy_version": "policy:2026.08.10",
    "feature_schema_version": "features:v4"
  },
  "execution": {
    "layers_executed": ["payload_validation", "features", "hard_rules", "business_rules", "cold_start_model", "calibration", "policy"],
    "layers_skipped": ["hbos", "global_model"],
    "terminating_layer": "policy",
    "risk_escalating_layer": "business_rules",
    "fallback_reason": null,
    "latency_ms": 41.7,
    "shadow_mode": false
  },
  "policy": {
    "cohort": "sem_historico",
    "thresholds_version": "thresholds:2026.08.10",
    "challenge_band": { "lower": 0.45, "upper": 0.8 },
    "step_up_eligible": true
  },
  "transaction_context": {
    "amount": 480.0,
    "currency": "BRL",
    "channel": "ecommerce",
    "product": "private_label",
    "transaction_type": "compra",
    "installments": 3,
    "merchant": { "id": "mch_2213", "mcc": "5651", "is_new_for_subject": true },
    "device": { "fingerprint_token": "dev_a91f", "is_new_for_subject": true },
    "geo": { "country": "BR", "region": "SP", "precision": "cidade" }
  }
}
```

## Critérios de aceite

- 100% das transações classificadas como `challenge` publicam o evento, validado contra o
  schema antes da publicação.
- Publicação do evento não integra o caminho síncrono da resposta HTTP e não afeta o p95.
- Falha na publicação é detectada e reconciliada: nenhum `challenge` fica sem evento
  correspondente, comprovado por conciliação entre decisões e eventos publicados.
- Entregas duplicadas não geram caso duplicado, notificação duplicada nem reexecução de
  validador, verificado por teste de idempotência.
- Nenhum campo do evento contém CPF em claro, verificado por teste automatizado de contrato.
