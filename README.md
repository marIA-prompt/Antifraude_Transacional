# Motor de Score Antifraude — base documental e contratos

Repositório de arquitetura, contratos e critérios de aceite do microserviço de score antifraude.
Não contém o runtime do motor: contém a especificação verificável da arquitetura atual e da evolução
proposta.

Cada documento separa explicitamente **AS-IS** (o que existe), **Lacuna/Risco**, **TO-BE** (evolução
proposta) e **critério de aceite** (como comprovar a entrega). AutoML, agentes de IA e Agent
Framework Workflows **não estão em produção** — são evoluções planejadas.

## Por onde começar

| Se você quer... | Leia |
| --- | --- |
| Entender o sistema como ele é hoje | [`docs/arquitetura/as-is.md`](docs/arquitetura/as-is.md) |
| Saber o que está errado e quão grave é | [`docs/arquitetura/lacunas-e-riscos.md`](docs/arquitetura/lacunas-e-riscos.md) |
| Ver a arquitetura alvo e as decisões | [`docs/arquitetura/to-be.md`](docs/arquitetura/to-be.md) |
| Executar a próxima entrega | [`docs/evolucoes/`](docs/evolucoes/) |
| Integrar com o serviço | [`docs/contratos/`](docs/contratos/) |
| Treinar, avaliar ou promover modelo | [`docs/mlops/`](docs/mlops/) |
| Tratar dado pessoal e exposição de lógica | [`docs/governanca/lgpd-e-dados-sensiveis.md`](docs/governanca/lgpd-e-dados-sensiveis.md) |
| Ler o briefing original, sem interpretação | [`docs/contexto-operacional.md`](docs/contexto-operacional.md) |

## Resumo em uma página

**AS-IS.** Microserviço de decisão online em cascata com short-circuit: validação de payload,
cálculo de features, HBOS individual por CPF, regras de negócio e hard rules, XGBoost global,
decisão `approve` / `challenge` / `deny`, logs de auditoria. Meta de p95 abaixo de 100 ms no fast
path. Os diagramas do produto mostram ainda que a regra 83 funciona como porta de entrada do motor e
que há confirmação por WhatsApp para os casos que ela aciona.

**Lacunas principais.** O `challenge` não tem fluxo operacional; a resposta HTTP expõe apenas
`decision_final`; o cache de modelo não invalida após retreino; CPF novo é aprovado por padrão; o
short-circuit esconde a performance das camadas posteriores e enviesa o retreinamento; rótulo imaturo
tratado como legítimo corrompe a avaliação supervisionada.

**TO-BE.** Separar o hot path determinístico da trilha de tratamento de risco. `challenge` publica
`fraud.challenge.created` e é resolvido de forma assíncrona por validadores com timeout, circuit
breaker e fallback, com desfecho rastreável e notificação idempotente. Contrato versionado: v1
inalterada, v2 com explicabilidade sob autenticação e autorização por perfil. Publicação atômica de
modelo com evento, invalidação de cache e rollback rápido. Política de cold start configurável por
valor, canal e produto, com peso do HBOS proporcional à confiança do histórico.

**Ordem de execução.** Observabilidade da cascata → `challenge` operacional → publicação de modelos e
cache → cold start → agentes de IA como apoio assíncrono à triagem, sempre depois dos controles
determinísticos e nunca substituindo hard rules.

## Estrutura

```text
docs/
  contexto-operacional.md          briefing fonte, cópia fiel
  arquitetura/
    as-is.md                       estado atual, divergências entre fontes, diagramas
    lacunas-e-riscos.md            registro LR-01..LR-16 com severidade e evidência
    to-be.md                       arquitetura alvo, orçamento de latência, enumerações canônicas
  evolucoes/
    01-challenge-operacional.md    prioridade 1: fila, validadores, step-up, desfecho rastreável
    02-publicacao-de-modelos-e-cache.md
    03-cold-start.md
  mlops/
    observabilidade-e-shadow.md    decision trace e amostra de 1% a 5%
    dados-e-validacao-temporal.md  qualidade, leakage, maturação de rótulos, drift
    promocao-e-rollout.md          AutoML permitido/não permitido, métricas, registry, rollback
    vies-e-equidade.md             coortes, proxies, reversões
  contratos/
    openapi-v1.yaml                AS-IS congelado (decision_final)
    openapi-v2.yaml                TO-BE com explicabilidade autorizada
    schemas/                       decision trace, eventos e resultado de validador
    exemplos/                      payloads que validam contra os schemas
    reason-codes.md                catálogo com exposição por perfil
  governanca/
    lgpd-e-dados-sensiveis.md      minimização, retenção, exposição da lógica
tools/
  validate_contracts.py            valida schemas, exemplos, OpenAPI e invariantes
```

## Validando os contratos

```bash
python3 -m pip install -r requirements-dev.txt
python3 tools/validate_contracts.py
```

A validação cobre o metaschema dos JSON Schemas, cada exemplo contra seu schema, o parse dos dois
contratos OpenAPI, a existência de todo reason code no catálogo, a regra de score `null` para camada
não executada e testes negativos que provam que as invariantes são rejeitadas quando violadas — como
publicação de modelo com artefato não verificado ou validador em timeout sem fallback declarado.
