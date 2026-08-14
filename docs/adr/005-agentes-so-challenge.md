# ADR-005 — Agentes de IA somente na trilha de challenge

## Status

Aceito

## Contexto

Microsoft Agent Framework Workflows é evolução planejada, não produção. Usá-lo
no hot path quebraria latência e determinismo. Substitui-lo por hard rules em
decisões críticas quebraria auditabilidade.

## Decisão

Agentes só após evento de challenge e após validadores determinísticos
(regras adicionais, blocklist/bureau, geo/device, histórico estendido). Cada
validador tem contrato, timeout, circuit breaker e fallback seguro. Agentes
apoiam triagem; não autorizam sozinhos.

## Consequências

- Prioridade 1 do roadmap não inclui agentes.
- Hard rules continuam soberanas.
