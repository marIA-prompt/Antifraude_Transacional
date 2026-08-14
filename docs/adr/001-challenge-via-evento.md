# ADR-001 — Challenge via evento interno

## Status

Aceito

## Contexto

A HTTP v1 pode expor somente `decision_final`. O orquestrador de challenge
precisa de scores, sinais, features, versões e contexto da transação.

## Decisão

Publicar `fraud.challenge.created` (outbox) com o payload mínimo definido no
contexto operacional. O autorizador continua sincrono e mínimo. O workflow
assíncrono consome o evento, não a resposta HTTP v1.

## Consequências

- Retrocompatibilidade do autorizador.
- Exige persistência idempotente e fila.
- Evita vazar explicabilidade na borda pública.
