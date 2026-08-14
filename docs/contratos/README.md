# Contratos

Artefatos machine-readable do motor antifraude. São a forma verificável dos critérios de aceite:
schema rejeita registro incompleto, e o script de validação prova que os exemplos estão coerentes
com os schemas.

## Inventário

| Artefato | Estado | Papel |
| --- | --- | --- |
| [`openapi-v1.yaml`](openapi-v1.yaml) | AS-IS, congelado | Resposta HTTP com apenas `decision_final` |
| [`openapi-v2.yaml`](openapi-v2.yaml) | TO-BE, não implementado | Explicabilidade sob autenticação e autorização por perfil |
| [`schemas/decision-trace.schema.json`](schemas/decision-trace.schema.json) | TO-BE | Um registro por transação, com camadas executadas e suprimidas |
| [`schemas/fraud.challenge.created.schema.json`](schemas/fraud.challenge.created.schema.json) | TO-BE | Evento que inicia a trilha de `challenge` |
| [`schemas/validator-result.schema.json`](schemas/validator-result.schema.json) | TO-BE | Saída de cada validador do workflow |
| [`schemas/challenge.outcome.recorded.schema.json`](schemas/challenge.outcome.recorded.schema.json) | TO-BE | Desfecho rastreável do `challenge` |
| [`schemas/model.published.schema.json`](schemas/model.published.schema.json) | TO-BE | Publicação e promoção de versão de modelo |
| [`reason-codes.md`](reason-codes.md) | TO-BE | Catálogo com exposição por perfil |

## Invariantes que os schemas garantem

- **Score de camada não executada é `null`, nunca `0`.** `0` é um score válido: confundir os dois
  corrompe qualquer agregação e esconde o efeito do short-circuit.
- **`reason_codes` tem no mínimo um item.** Decisão sem reason code é inválida, não genérica.
- **Falha de validador exige fallback declarado.** `timeout`, `error` e `circuit_open` obrigam
  `fallback_applied: true` e `fallback_reason_code`.
- **Encerramento antecipado exige `deny` de alta confiança.** `terminates_workflow: true` só é válido
  com `outcome: deny` e `confidence: high`.
- **CPF nunca em claro fora do hot path.** `cpf_token` obedece ao padrão `tok_...`; o CPF só aparece
  no request da API.
- **Publicação exige integridade e compatibilidade.** `integrity_verified` e `compatible` são `const:
  true`: artefato não verificado não gera evento válido.
- **Promoção a champion do modelo supervisionado exige métricas, instantâneo de rótulos e janela
  temporal.**
- **Invalidação `by_key` exige a lista de chaves**, para não degenerar em invalidação global dos
  bundles por CPF.
- **Idempotência é dado de contrato**: `idempotency_key` derivada de `transaction_id` +
  `correlation_id` liga o evento de challenge ao seu desfecho, sustentando CA-1.1 e CA-1.4.

## Validação

```bash
python3 -m pip install -r requirements-dev.txt
python3 tools/validate_contracts.py
```

O script valida os schemas contra o metaschema JSON Schema 2020-12, valida cada exemplo de
[`exemplos/`](exemplos/) contra o schema correspondente, faz o parse dos dois arquivos OpenAPI e
verifica invariantes de projeto que o schema não expressa sozinho — entre elas que todo reason code
usado nos exemplos existe no catálogo e que a v1 continua expondo apenas `decision_final`.

## Versionamento

- Schemas usam versionamento semântico no `$id` e campo `schema_version` no payload.
- Mudança compatível (campo opcional novo): incrementa a versão menor.
- Mudança incompatível (campo obrigatório, remoção, alteração de enum): nova versão maior, com
  período de coexistência entre produtor e consumidores.
- A v1 da API HTTP não recebe campos novos: consumidor que precisa de mais dado migra para a v2.
