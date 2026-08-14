# Evolução do Motor de Score Antifraude

Pacote de arquitetura e contratos para a evolução do microserviço de score
antifraude (cartão private label). Este repositório **não** afirma que AutoML,
Agent Framework ou orquestração de `challenge` já estejam em produção.

| Camada | Conteúdo |
| --- | --- |
| Documentação | AS-IS, lacunas, TO-BE, LGPD, MLOps e critérios de aceite |
| Contratos | OpenAPI v1/v2 e JSON Schema dos eventos |
| Simulador | Política determinística de decisão + emissão de `challenge` |
| Testes | Critérios de aceite executáveis |

## Como ler

1. [Visão AS-IS](docs/01-as-is.md)
2. [Lacunas e riscos](docs/02-lacunas-e-riscos.md)
3. [Arquitetura TO-BE](docs/03-to-be-arquitetura.md)
4. [Contratos de API](docs/04-contratos-api.md)
5. [Challenge operacional](docs/05-challenge-operacional.md)
6. [Publicação de modelos e cache](docs/06-publicacao-modelos-e-cache.md)
7. [Política de cold start](docs/07-politica-cold-start.md)
8. [Observabilidade, shadow e MLOps](docs/08-observabilidade-shadow-mlops.md)
9. [LGPD, viés e governança](docs/09-lgpd-vies-governanca.md)
10. [Roadmap e critérios de aceite](docs/10-roadmap-criterios-aceite.md)
11. [Diagramas](docs/diagramas.md)
12. [ADRs](docs/adr/README.md)

## Princípios obrigatórios

- **HBOS** é detector de anomalia individual por CPF, não prova de fraude.
- **XGBoost** é classificador supervisionado dependente de rótulos maduros e split temporal.
- **AutoML** só é permitido offline; nunca no hot path de autorização.
- **Agentes de IA** só entram na trilha assíncrona de `challenge`, depois de hard rules.
- A API HTTP **v1** pode expor somente `decision_final`. O orquestrador de `challenge` não depende dela.
- Fast path de approve/deny: **p95 < 100 ms**.

## Simulador e testes

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
```

O simulador ilustra a política TO-BE (cascata, short-circuit, cold start,
evento de challenge e versões de modelo). Não substitui o microserviço de produção.
