# Motor de Score Antifraude — arquitetura e decisões

Repositório de arquitetura, contratos e decisões técnicas do microserviço FastAPI de score
antifraude (`POST /api/v1/score-transaction`).

Todo documento separa **AS-IS**, **Lacuna/Risco**, **TO-BE** e **Critério de aceite**.

> AutoML, agentes de IA e Agent Framework Workflows **não estão em produção**.
>
> A quantidade de features **não é definitiva** enquanto
> [`contracts/features/registry.json`](contracts/features/registry.json) estiver
> `unreconciled` (divergência 10 × 13).
>
> NEG83 / Motor H **não** são tratados como gate deste microserviço enquanto D-3 estiver
> aberto.

Briefing normativo: [`docs/contexto-operacional.md`](docs/contexto-operacional.md).

## Índice

### Contexto

- [Mapa mental](docs/mapa-mental.md) — comece aqui.
- [Contexto AS-IS](docs/arquitetura/00-contexto-as-is.md)
- [Divergências documentais](docs/arquitetura/divergencias-documentais.md) — API, 10×13,
  NEG83, ordem da cascata
- [Orçamento de latência](docs/arquitetura/orcamento-de-latencia.md) — p95 < 100 ms

### Decisões (ADR)

- [ADR-0001 — Cascata, short-circuit e escada de degradação](docs/adr/0001-topologia-de-decisao.md)
- [ADR-0002 — Papéis dos modelos](docs/adr/0002-papeis-dos-modelos.md)
- [ADR-0003 — Cold start](docs/adr/0003-politica-de-cold-start.md)
- [ADR-0004 — Publicação de modelos e cache](docs/adr/0004-publicacao-de-modelos-e-cache.md)

### Contratos

- [API v1/v2](docs/contratos/api-versionada.md) · OpenAPI [`contracts/openapi/score-api.yaml`](contracts/openapi/score-api.yaml)
- [Evento `fraud.challenge.created`](docs/contratos/evento-challenge.md) · [`contracts/events/fraud.challenge.created.schema.json`](contracts/events/fraud.challenge.created.schema.json)
- [Registry de features](docs/contratos/features.md) · [`contracts/features/registry.json`](contracts/features/registry.json)
- [Reason codes](docs/contratos/reason-codes.md)

### Operação e MLOps

- [Trilha de challenge](docs/workflows/trilha-de-challenge.md)
- [Dados, rótulos, viés e promoção](docs/mlops/dados-rotulos-e-promocao.md)
- [Acompanhamento de modelagem (MAPA)](docs/mlops/acompanhamento-modelagem.md)
- [Telemetria e shadow](docs/observabilidade/telemetria-de-decisao.md)
- [LGPD](docs/governanca/lgpd-e-dados-sensiveis.md)
- [Motor H / NEG83](docs/recuperacao/motor-h-neg83.md) — ranking de recuperação, fora do hot path

### Execução

- [Roadmap por fases](docs/roadmap.md)

## Validação dos contratos

```bash
pip install -r requirements-dev.txt
python3 scripts/validate_contracts.py
```

Verifica JSON Schema, OpenAPI, exemplo do evento, v1 restrita a `decision_final`, ausência
de CPF em claro, registry de features `unreconciled` sem lista canônica, e path
`/api/v1/score-transaction`.

## Ordem de prioridade

1. Instrumentar short-circuit e shadow; conciliar D-2 e D-3.
2. Operacionalizar `challenge`.
3. Invalidação de cache sem restart.
4. Cold start configurável.
5. Só então AutoML offline / agentes na trilha assíncrona.

Agentes de IA não substituem hard rules. Motor H não entra na cascata HBOS/XGBoost.
