# Motor de Score Antifraude

Implementação de referência do fluxo de decisão antifraude descrito em
[`docs/CONTEXTO_OPERACIONAL.md`](docs/CONTEXTO_OPERACIONAL.md), com foco nas evoluções
prioritárias definidas nesse contexto: **operacionalização do `challenge`**, **invalidação de
cache de modelos** e **política de cold start**.

> **Leia primeiro**: este código é um *scaffold* de arquitetura e testes, não um serviço em
> produção. HBOS e XGBoost são interfaces com implementações de referência determinísticas
> (não são modelos treinados); mensageria, cache distribuído, banco de auditoria e
> integrações externas (bureau, blocklist, geolocalização, device intelligence) são
> interfaces com implementações em memória para desenvolvimento e teste. AutoML, agentes de
> IA e o Microsoft Agent Framework Workflows real **não estão implementados nem em produção**
> — são evoluções futuras, conforme a diretriz do contexto operacional.

## Por que este repositório existe

O contexto operacional pede que qualquer resposta sobre este projeto diferencie **AS-IS**,
**Lacuna/Risco**, **TO-BE** e **Critério de aceite**. Este código materializa essa distinção:
cada módulo documenta explicitamente o que é comportamento AS-IS reproduzido fielmente, o que
é uma lacuna conhecida e o que é uma implementação de referência do TO-BE proposto. Veja a
pasta [`docs/`](docs/) para o detalhamento completo por tema.

## Estrutura

```text
src/antifraud/
  domain/        Modelos e enums de domínio (Transaction, Decision, DecisionTrace, ...)
  validation/    Validação de payload (AS-IS: passo 1 da cascata)
  features/      Cálculo de features e perfil de cliente (histórico/cold start)
  models_ml/     Interfaces HBOS/XGBoost, model registry e invalidação de cache
  rules/         Motor de regras de negócio e hard rules
  coldstart/     Política de cold start (Evolução prioritária 3)
  decision/      Orquestrador da cascata de decisão (short-circuit + observabilidade)
  challenge/     Operacionalização do challenge (Evolução prioritária 1)
  audit/         Sinks de auditoria (registro completo por transação)
  api/           API v1 (decision_final) e v2 (explicabilidade, autenticada)
  service.py     Fachada que une cascata + auditoria + challenge

docs/
  CONTEXTO_OPERACIONAL.md   Documento-fonte completo (papel, AS-IS, TO-BE, diretrizes)
  ARCHITECTURE.md           Fluxo de decisão em cascata e pontos de extensão
  API.md                    Contrato v1/v2, autenticação e mascaramento
  CHALLENGE_WORKFLOW.md     Sequência de operacionalização do challenge e cobertura de teste
  MODEL_LIFECYCLE.md        Invalidação de cache e publicação de modelos
  COLD_START.md             Política de cold start
  MLOPS_GOVERNANCE.md       AutoML, viés, drift, LGPD, rotulagem (diretrizes, sem código)

tests/           Suíte pytest cobrindo cascata, regras, cold start, challenge, workflow,
                 invalidação de cache e contrato de API
```

## Como rodar

```bash
pip install -e ".[dev]"
pytest -q
```

Subir a API localmente (implementações em memória, apenas para exploração manual):

```bash
uvicorn antifraud.api.app:app --reload
```

Exemplos de chamada:

```bash
curl -X POST http://127.0.0.1:8000/v1/transactions/authorize \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"tx-1","correlation_id":"corr-1","cpf":"12345678900","amount":150.0}'

curl -X POST http://127.0.0.1:8000/v2/transactions/authorize \
  -H "Content-Type: application/json" -H "X-API-Key: demo-analyst-key" \
  -d '{"transaction_id":"tx-2","correlation_id":"corr-2","cpf":"12345678900","amount":150.0}'
```

## Cobertura de critérios de aceite

Cada documento em `docs/` lista os critérios de aceite do contexto operacional e aponta o(s)
teste(s) que os comprovam. Resumo do que é comprovado por teste automatizado hoje:

- 100% dos casos `challenge` produzem um desfecho rastreável (`approve`/`deny`/`escalate`).
- Toda transação (mesmo rejeitada ou encerrada por short-circuit) gera um `DecisionTrace`
  completo, com camadas executadas/não executadas.
- Toda hard rule e regra de negócio acionada gera evidência e reason code.
- Cada validador do workflow de challenge registra duração, resultado, erro, timeout e uso de
  fallback; validadores lentos/quebrados nunca bloqueiam indefinidamente a decisão.
- O fluxo de challenge é idempotente por `transaction_id` + `correlation_id` (evento publicado
  uma única vez; reprocessamento do workflow retorna o mesmo resultado).
- Publicação de modelo (`model.published`) invalida cache sem exigir restart; rollback rápido
  disponível no model registry.
- A API v1 expõe exclusivamente `decision_final`; a v2 exige autenticação, aplica mascaramento
  por perfil e não é a fonte de dados do orquestrador de challenge.

O que **não** é comprovado por teste (por ser explicitamente fora de escopo): treinamento real
de modelos, métricas de drift/viés, pipeline de rotulagem, dashboards de monitoramento e
qualquer integração com AutoML ou agentes de IA — ver `docs/MLOPS_GOVERNANCE.md`.
