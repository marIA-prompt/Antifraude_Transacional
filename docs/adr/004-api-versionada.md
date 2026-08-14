# ADR-004 — API v1 estável e API v2 de explicabilidade

## Status

Aceito

## Contexto

Há divergência entre a especificação original (cinco campos) e a HTTP atual
(`decision_final`). Ampliar a v1 quebra clientes ou expõe lógica.

## Decisão

- v1: `{ "decision_final": "approve|challenge|deny" }`, retrocompatível.
- v2: contrato rico, autenticação, autorização por perfil, mascaramento LGPD
  e recusa de campos que revelem indevidamente a lógica antifraude.

## Consequências

- Dois contratos OpenAPI versionados.
- Feature flags / scopes para `features` e `feature_weights`.
