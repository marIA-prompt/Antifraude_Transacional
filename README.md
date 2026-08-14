# Motor de Score Antifraude — arquitetura e decisões

Repositório de arquitetura, contratos e decisões técnicas do microserviço de score antifraude
para transações de cartão de crédito.

Todo documento aqui separa explicitamente **AS-IS** (o que existe), **Lacuna/Risco**,
**TO-BE** (evolução proposta) e **Critério de aceite** (como comprovar a entrega).

> AutoML, agentes de IA e orquestração por workflows **não estão em produção**. São evoluções
> planejadas e estão descritas como tal.

## Índice

### Contexto

- [Contexto AS-IS do motor de score](docs/arquitetura/00-contexto-as-is.md) — fluxo vigente
  (gate da Regra 83), componentes de decisão, lacunas consolidadas e perguntas abertas.

### Decisões de arquitetura (ADR)

- [ADR-0001 — Topologia de decisão: avaliação paralela e camada de política](docs/adr/0001-topologia-de-decisao.md)
- [ADR-0002 — Papéis dos modelos: HBOS, GBDT global, calibração e consolidação](docs/adr/0002-papeis-dos-modelos.md)
- [ADR-0003 — Política de cold start](docs/adr/0003-politica-de-cold-start.md)
- [ADR-0004 — Publicação de modelos e invalidação de cache](docs/adr/0004-publicacao-de-modelos-e-cache.md)

### Contratos

- [API versionada v1/v2](docs/contratos/api-versionada.md) · OpenAPI: [`contracts/openapi/score-api.yaml`](contracts/openapi/score-api.yaml)
- [Evento `fraud.challenge.created`](docs/contratos/evento-challenge.md) · JSON Schema: [`contracts/events/fraud.challenge.created.schema.json`](contracts/events/fraud.challenge.created.schema.json)

### Operação e MLOps

- [Trilha de challenge: fila, validadores e step-up](docs/workflows/trilha-de-challenge.md)
- [Dados, rótulos, viés e promoção de modelos](docs/mlops/dados-rotulos-e-promocao.md)
- [Telemetria de decisão, short-circuit e shadow](docs/observabilidade/telemetria-de-decisao.md)

### Execução

- [Roadmap por fases com critérios de aceite](docs/roadmap.md)

## Validação dos contratos

Os contratos versionados são validados por script, para que a divergência entre documentação e
schema falhe de forma visível:

```bash
pip install -r requirements-dev.txt
python3 scripts/validate_contracts.py
```

As verificações cobrem a validade do JSON Schema e do OpenAPI, a conformidade do exemplo
documentado do evento com o schema, a restrição da resposta v1 a `decision_final` e a ausência de
CPF em claro em qualquer contrato.

## Ordem de prioridade acordada

1. Operacionalizar `challenge` (com a instrumentação de telemetria e shadow em conjunto).
2. Invalidação de cache e publicação de modelos sem restart.
3. Política de cold start configurável.
4. Somente então expandir modelos novos e agentes de IA assíncronos.

Agentes de IA não substituem hard rules nem políticas determinísticas em decisões críticas.
