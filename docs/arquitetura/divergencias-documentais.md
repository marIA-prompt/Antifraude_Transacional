# Divergências documentais abertas

> **AS-IS da conciliação:** duas divergências estão registradas no briefing versão final
> (contrato da API e quantidade de features). Uma terceira foi identificada ao incorporar as
> fontes de acompanhamento de modelagem e do Motor H, e permanece **aberta** — não foi
> homogeneizada.

Enquanto um item estiver aberto, **nenhum documento deste repositório deve afirmar uma das
leituras como produção**. A conciliação exige evidência de código ou de telemetria, não
harmonização editorial.

## D-1 — Contrato da API

| Camada | Conteúdo |
|---|---|
| **AS-IS (especificação do microserviço)** | Resposta com `score`, `decision`, `signals`, `features`, `feature_weights` |
| **AS-IS (implementação)** | `{ "decision_final": "approve \| challenge \| deny" }` |
| **Lacuna/Risco** | Integrador não vê score/sinais na HTTP; detalhe só no log. Orquestração tentada sobre a v1 acopla o hot path a consumidores de explicabilidade e expõe lógica antifraude |
| **TO-BE** | v1 congelada com `decision_final`. v2 com explicabilidade sob autenticação, autorização por perfil, mascaramento e rate limiting. Orquestrador de `challenge` consome [`fraud.challenge.created`](../contratos/evento-challenge.md) |
| **Critério de aceite** | Teste de contrato: v1 permanece restrita a `decision_final` (`additionalProperties: false`). Nenhum consumidor da v1 alterado. Perfil sem escopo na v2 recebe `403`. CPF em claro ausente nos contratos. Critério 9 do briefing |

Referência normativa: [`api-versionada.md`](../contratos/api-versionada.md). Endpoint AS-IS:
`POST /api/v1/score-transaction`.

## D-2 — Quantidade de features (10 × 13)

| Fonte | Quantidade | Natureza |
|---|---|---|
| Apresentação AS-IS | 13 features + regras + hard-rule geográfica | Especificação anterior |
| PDF do microserviço | 10 features numéricas | Implementação descrita no PDF |

| Camada | Conteúdo |
|---|---|
| **AS-IS** | As duas cifras coexistem em documentação. **Nenhuma é canônica.** Os nomes não aparecem nas fontes. |
| **Lacuna/Risco** | Treino, inferência e explicabilidade podem divergir de schema. Um número afirmado agora vira dívida invisível no registry |
| **TO-BE** | Listas **candidatas** nomeadas em [`contracts/features/registry.json`](../../contracts/features/registry.json) (`status: candidate`, schema `features:candidate-2026.08.25`): 10 a partir dos perfis do bundle HBOS; 13 = essas 10 + `log_amount`, `is_night`, `tx_count_24h` (hipótese H1). Promoção a `reconciled` só após auditoria do FastAPI de produção |
| **Critério de aceite (agora)** | `canonical_list` continua `null`. `candidate_pdf_10` tem 10 nomes; `candidate_apresentacao_13` tem 13 e prefixo igual aos 10. Teste em `scripts/validate_contracts.py` |
| **Critério de aceite (fechamento D-2)** | `status = reconciled`, `audited_production_code = true`, cada feature com nome, tipo, instante de disponibilidade e leakage. Critério 11 do briefing. Qualquer texto que trate 10 ou 13 como definitivo **antes** disso está errado |

Este repositório **não contém o código de produção do microserviço**. Scaffold (7 stubs) e
pipeline sintético (10 `COLD_START_FEATURES`) não fecham D-2.

## D-3 — Relação entre NEG83 / Motor H e o microserviço de score

Terceira divergência, **não** listada no briefing, identificada ao consolidar as fontes
anexas.

| Fonte | O que descreve |
|---|---|
| Briefing versão final (este repositório, 2026-08-25) | Microserviço FastAPI de score; cascata HBOS → (condicional) XGBoost; **não** descreve a Regra 83 como gate deste serviço |
| MAPA de acompanhamento (Osterne / Morais) | Regra 83 como *gate* dos modelos: transações que não a acionam são aprovadas sem escore; as demais passam por HBOS e, em reprovação/dúvida, por XGBoost. O próprio MAPA classifica isso como premissa a confirmar na Etapa 1 |
| Motor H (agosto 2026) | Jornada `Transação → Autenticador → NEG83 → Bloqueio WhatsApp → Confirmação → Nova tentativa`. Motor H **não prevê fraude**: ordena jornadas NEG83 pela propensão a `LATER_SUCCESS`. 33 features de `FIRST_NEG83`. Fora do hot path de autorização |

| Camada | Conteúdo |
|---|---|
| **AS-IS** | Existem (pelo menos) dois artefatos distintos: o **motor de score FastAPI** (HBOS + XGBoost) e o **estudo Motor H** sobre recuperação de NEG83. A composição operacional entre eles **não está confirmada** |
| **Lacuna/Risco** | Tratar NEG83 como gate deste microserviço sem evidência reproduz a leitura que o briefing versão final deixou de adotar. Ignorar NEG83 apaga um fluxo real de fricção (WhatsApp) e um modelo de ranking já avaliado (Motor H). Confundir os dois mistura target de fraude com target de recuperação |
| **TO-BE** | Confirmar com trace de produção (Etapa 1 do [MAPA](../mlops/acompanhamento-modelagem.md)): (a) NEG83 é autenticador/bloqueio **antes** do score; (b) NEG83 **é** o gate do score; ou (c) são produtos paralelos. Documentar a topologia escolhida. Motor H permanece estudo até teste assistido |
| **Critério de aceite** | Um diagrama AS-IS único, datado, com evidência (trace ou código) da ordem Autenticador / NEG83 / `POST /api/v1/score-transaction`. Até lá, D-3 permanece aberto |

Detalhamento do estudo: [`motor-h-neg83.md`](../recuperacao/motor-h-neg83.md).

## D-4 — Ordem da cascata HBOS × XGBoost (histórico do repositório)

A documentação anterior deste repositório (PR #1, ago/2026) descreveu o AS-IS como *approve
terminal do HBOS* e XGBoost emitindo a decisão final, inclusive revertendo reprovação. O
briefing versão final descreve o inverso no short-circuit: **`HBOS = deny` encerra sem
XGBoost**; XGBoost roda quando HBOS é `approve` ou `challenge`.

| Camada | Conteúdo |
|---|---|
| **AS-IS (briefing versão final)** | `HBOS = deny` → decisão final `deny`; XGBoost não executa |
| **Lacuna/Risco** | A leitura anterior do repositório não deve ser citada como produção. Sem `short_circuit_layer` no log, a ordem efetiva continua sendo inferência |
| **TO-BE** | Instrumentar `layers_executed`, `layers_skipped`, `short_circuit_layer` em 100% das transações. Amostra shadow 1%–5% executa o XGBoost também nos `deny` do HBOS, sem afetar a decisão |
| **Critério de aceite** | 100% das decisões com `short_circuit_layer` preenchido (`hbos` ou `null`). Score de camada não executada é `null`, nunca `0`. Relatório mensal de divergência HBOS/XGB na amostra shadow |

## Como conciliar

Ordem obrigatória, porque cada passo desbloqueia o seguinte:

1. **Instrumentar o decision trace** (D-4, L4) — sem isso, D-3 e D-2 não saem do papel.
2. **Auditar o código de features** e publicar o registry (D-2).
3. **Confirmar a topologia NEG83 × score** com o time e com trace (D-3, MAPA Etapa 1).
4. **Publicar a API v2** sem alterar a v1 (D-1).
