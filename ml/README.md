# Pipeline de treino do motor de score antifraude

Ponto de partida executável para treinar os modelos descritos nos ADRs, começando
com **dados sintéticos LGPD-safe** (fictícios, mas com comportamento estatístico
idêntico ao de produção) e evoluindo depois para dados reais tokenizados.

O pipeline implementa fielmente as decisões de arquitetura:

- **GBDT global** (champion supervisionado) + **GBDT de cold start** sem features de
  histórico do CPF ([ADR-0002](../docs/adr/0002-papeis-dos-modelos.md)).
- **HBOS individual por CPF** como sinal comportamental, com peso por coorte e nunca
  decisor ([ADR-0002](../docs/adr/0002-papeis-dos-modelos.md), [ADR-0003](../docs/adr/0003-politica-de-cold-start.md)).
- **Calibração isotônica** versionada, ajustada por coorte ([ADR-0002](../docs/adr/0002-papeis-dos-modelos.md)).
- **Split temporal** obrigatório, **gates de qualidade bloqueantes**, e a regra de que
  `sem_desfecho` nunca é negativa ([MLOps](../docs/mlops/dados-rotulos-e-promocao.md)).

## Como rodar

```bash
pip install -r ml/requirements.txt

# 1. Gera o dataset sintético (LGPD-safe)
python3 -m ml.generate_synthetic --config ml/config.yaml --out ml/data

# 2. Treina modelos, calibra, avalia por coorte e grava artefatos
python3 -m ml.train --config ml/config.yaml --data ml/data/transactions.csv --out ml/artifacts

# 3. (opcional) Garantias do pipeline (LGPD, leakage, gates, rótulos)
python3 -m ml.selftest
```

Saídas em `ml/artifacts/`: `models.joblib`, `metrics.json`, `report.md` e
`model_registry.json` (estado `candidate`, versões e metadados do split temporal).

---

## Respostas às perguntas de dados

### 1. Dados de todas as transações? Qual o volume necessário?

**Sim — de todas as transações autorizadas, não apenas as que caem na Regra 83.**
Treinar só no recorte do gate é viés de seleção estrutural e invalida qualquer métrica
de promoção ([MLOps](../docs/mlops/dados-rotulos-e-promocao.md), L1). O desenho TO-BE
([ADR-0001](../docs/adr/0001-topologia-de-decisao.md)) dá **cobertura de ML em 100% do
tráfego autorizado**, complementado por **shadow scoring de 1%–5% do tráfego fora do
gate** para observar a fraude que a regra deixa passar.

O que dimensiona o dataset não é o total de linhas, e sim o número de **fraudes
confirmadas maduras**. Referências práticas:

| Objetivo | Fraudes confirmadas maduras | Transações (@ ~1% de fraude) | Janela |
|---|---|---|---|
| Protótipo / bootstrap (este repo) | ~1.000–5.000 | ~100 mil – 500 mil | ≥ 6–12 meses |
| Modelo global estável | ~10.000+ | ~1–5 milhões | ≥ 12 meses |
| Quebra confiável por coorte (cold start, canal, região) | ~30.000+ | ~5–15 milhões | 12–24 meses |

Regras que valem sempre:

- **Janela ≥ 12 meses** para capturar sazonalidade e respeitar a **maturação de rótulo**:
  o mês mais recente ainda não tem desfecho estável e não entra como negativa.
- **Não reamostrar cegamente.** Mantenha a prevalência real e trate a raridade com
  métricas (PR-AUC, recall) e thresholds — reamostragem agressiva quebra a calibração.
- **HBOS por CPF precisa de histórico por cliente** (janela de até ~730 dias; bundle
  pleno a partir de dezenas de transações). O dataset precisa conter CPFs com histórico
  **e** a coorte de CPF novo bem representada.
- Cubra as **quatro coortes de cold start** com positivos suficientes em cada uma.

O gerador default produz ~170 mil transações (6.000 CPFs, 12 meses), suficiente para o
pipeline rodar ponta a ponta; ajuste `generation.n_subjects` em `ml/config.yaml` para
escalar.

### 2. Como devem ser esses dados? (formato)

**Tabular colunar, uma linha por transação. Use Parquet (volume/produção) + CSV
(amostra/inspeção). Evite planilhas (Google Sheets/Excel)** para treino: não são
versionáveis, têm tipagem frágil, limite de linhas e risco de PII.

Boas práticas adotadas aqui:

- **Um arquivo por partição temporal** (ex.: por mês) facilita split temporal e
  reprocessamento incremental.
- **Timestamps em UTC** ISO-8601; **`subject_token` sempre tokenizado** (nunca CPF).
- **Rótulo maturado com 5 categorias** (não só binário), para aplicar a regra de
  maturação corretamente.
- **Esquema fixo e versionado** (`feature_schema_version`), validado por gates antes do
  treino.

### 3. Estrutura (dicionário de dados)

Colunas de `ml/data/transactions.csv` (equivalem a `ScoreRequest` + `transaction_context`
do evento `fraud.challenge.created`):

| Coluna | Tipo | Descrição |
|---|---|---|
| `transaction_id` | string (uuid) | Identificador único da transação |
| `subject_token` | string | **CPF tokenizado** — nunca o CPF em claro (LGPD) |
| `occurred_at` | datetime UTC | Instante da transação (ISO-8601) |
| `amount` | number | Valor da transação |
| `currency` | string(3) | Moeda (BRL) |
| `channel` | enum | ecommerce, pos, recurring, atm, wallet |
| `product` | enum | credit, private_label |
| `transaction_type` | enum | purchase, withdrawal, bill_payment, subscription |
| `installments` | int | Número de parcelas |
| `merchant_id` | string | Identificador do estabelecimento (tokenizado) |
| `mcc` | enum | Faixa de MCC (proxy de tipo de comércio) |
| `merchant_is_new_for_subject` | bool | Estabelecimento novo para o CPF |
| `device_fingerprint_token` | string | Device tokenizado |
| `device_is_new_for_subject` | bool | Device novo para o CPF |
| `geo_country` / `geo_region` | string | País / região (INTL quando fora do BR) |
| `geo_precision` | enum | gps, cell, ip, none |
| `ip_hash` | string | IP hasheado |
| `label_category` | enum | fraude_confirmada, fraude_suspeita, em_disputa, legitima_confirmada, sem_desfecho |
| `is_fraud` | bool | Verdade oculta para avaliação; **indisponível no scoring online** |

As features derivadas (histórico do CPF, velocity 24h/7d, z-score de valor, one-hots)
são construídas em `ml/features.py` com **segurança temporal** — cada transação só
enxerga o passado do próprio CPF.

## Estrutura do código

| Arquivo | Papel |
|---|---|
| `config.yaml` | Configuração versionada (coortes, janelas, gates) |
| `schema.py` | Colunas, coortes, categorias de rótulo e conjuntos de features |
| `generate_synthetic.py` | Gerador de dados sintéticos LGPD-safe |
| `data_quality.py` | Gates de qualidade bloqueantes |
| `features.py` | Feature engineering com segurança temporal |
| `hbos.py` | HBOS por CPF com contribuições por feature |
| `train.py` | Orquestração: split temporal, treino, calibração, avaliação, artefatos |
| `evaluate.py` | Conjunto mínimo de métricas de promoção, por coorte |
| `selftest.py` | Testes de garantia (LGPD, leakage, gates, rótulos) |

## Limites (honestos)

- Dados **sintéticos**: as métricas comprovam que o pipeline funciona ponta a ponta,
  não a performance em produção. Só dados reais tokenizados validam o modelo.
- Não há ainda features de grafo, shadow scoring nem model registry persistente —
  são os próximos passos previstos nos ADRs.
