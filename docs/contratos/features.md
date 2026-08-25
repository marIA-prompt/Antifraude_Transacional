# Contrato de features — schema registry

Normativo executável: [`contracts/features/registry.json`](../../contracts/features/registry.json)

Status atual: **`candidate`**. Há listas nomeadas. **Não há lista canônica.**
`canonical_list` permanece `null` porque o código de produção do FastAPI não está neste
repositório.

## AS-IS — o que as fontes realmente dizem

| Fonte | Cardinalidade | Nomes |
|---|---|---|
| PDF do microserviço | 10 numéricas | não lista nomes |
| Apresentação AS-IS | 13 + regras + hard-rule geográfica | não lista nomes |
| Bundle HBOS (briefing) | insumos de perfil, não o vetor | média do CPF, cartões, estabelecimentos, centróide geográfico |
| Pipeline sintético (`ml/schema.py`, outra branch) | 10 `COLD_START_FEATURES` + 9 de histórico + one-hots | TO-BE / offline, não o runtime |
| Scaffold `FeatureEngine` | 7 stubs | não é produção |
| Motor H `FIRST_NEG83` | 33 | **outro problema** — fora deste registry |

Regras (`valor_acima_padrao`, `estabelecimento_novo`) e a hard-rule `viagem_impossivel`
**não são features**. São sinais / reason codes. Hipótese H2 (o slide ter somado regras
no “13”) permanece aberta.

## Lacuna/Risco

Sem nomes versionados, treino, inferência e `feature_weights` da v2 divergem em silêncio.
Nulos > **2%** em feature crítica bloqueiam promoção — isso só é auditável com lista
nomeada. Afirmar 10 ou 13 como definitivo **continua proibido**.

## TO-BE — candidatas nomeadas (H1)

Derivadas dos perfis do bundle + payload da autorização. Candidata de 10 (PDF) e candidata
de 13 (apresentação = 10 + 3).

### Candidata PDF — 10 numéricas (`candidate_pdf_10`)

| # | Nome | Grupo | Insumo do bundle | Leakage | Crítica (nulos > 2%) |
|---|---|---|---|---|---|
| 1 | `amount` | payload | — | nenhum | sim |
| 2 | `amount_to_cpf_mean` | derived | média do CPF | só média **anterior** | sim |
| 3 | `hour_of_day` | payload | — | nenhum | sim |
| 4 | `day_of_week` | payload | — | nenhum | não |
| 5 | `installments` | payload | — | nenhum | sim |
| 6 | `merchant_is_new` | derived | estabelecimentos | conjunto **anterior** | sim |
| 7 | `card_is_new` | derived | cartões | conjunto **anterior** | sim |
| 8 | `distance_to_geo_centroid_km` | derived | centróide geográfico | centróide **anterior** | sim |
| 9 | `cpf_tx_count` | profile | histórico do CPF | contagem **anterior** | sim |
| 10 | `secs_since_last_tx` | derived | última transação | timestamp **anterior** | não |

### Candidata apresentação — 13 (`candidate_apresentacao_13` = 10 + 3)

| # | Nome | Por que entra na hipótese H1 |
|---|---|---|
| 11 | `log_amount` | escala log do valor; comum em HBOS |
| 12 | `is_night` | recorte de `hour_of_day`; regras de horário |
| 13 | `tx_count_24h` | velocity; não está no perfil estático do bundle |

`schema_version` desta candidatura: `features:candidate-2026.08.25`.

XGBoost global, no pipeline sintético, ainda usa extras de histórico
(`tx_count_7d`, `distinct_devices_prior`, `distinct_regions_prior`, `region_is_home`,
`device_is_new`, `geo_is_domestic`, `amount_zscore_pop`). Isso é **TO-BE de treino**, não
fecha D-2.

## Como promover a canônica

```text
Auditar o vetor que o FastAPI realmente monta no cálculo de features
→ se bater com candidate_pdf_10     → canonical_list = essa lista; status = reconciled; count = 10
→ se bater com candidate_apresentacao_13 → idem com 13
→ se for outro conjunto            → nova schema_version; NÃO reciclar o número 10 ou 13
→ feature_schema_version em toda publicação de modelo (ADR-0004)
```

Enquanto `audited_production_code = false`, promoção de modelo compara hash/versão opaca,
não a cardinalidade.

## Critérios de aceite

- `canonical_list` é `null` enquanto `status != reconciled`.
- `candidate_pdf_10` tem **exatamente 10** nomes únicos, todos presentes em `catalog`.
- `candidate_apresentacao_13` tem **exatamente 13** nomes, prefixo igual aos 10, mais
  `log_amount`, `is_night`, `tx_count_24h`.
- Motor H (33) e reason codes **não** aparecem nas candidatas.
- Nulos > 2% em `critical: true` bloqueiam promoção (gate do briefing).
- Teste em `scripts/validate_contracts.py` cobre os itens acima.
- Critério 11 do briefing só se encerra com `status: reconciled` após auditoria do código
  de produção.
