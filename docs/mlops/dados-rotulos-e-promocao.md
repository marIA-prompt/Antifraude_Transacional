# Dados, rótulos, viés e promoção de modelos

Protocolo diagnóstico em [acompanhamento-modelagem.md](acompanhamento-modelagem.md). Este
arquivo fixa controles contínuos e limiares numéricos do briefing.

## Lacuna/Risco: viés de seleção

Duas fontes possíveis, **nenhuma afirmada como exclusiva** enquanto D-3 e D-4 estiverem
abertos:

1. Gate operacional (NEG83 / Regra 83) se a Etapa 1 do MAPA confirmá-lo;
2. Short-circuit `HBOS = deny` (XGBoost não executa) — este está no briefing versão final.

Treinar e medir só no subconjunto que uma camada deixou passar é viés clássico. Enquanto
não houver amostra fora desse recorte, **nenhuma métrica de promoção é confiável**.

`sem_desfecho` **nunca** é classe negativa.

## TO-BE: dados não enviesados

**Shadow 1% a 5%** de todo o tráfego autorizado por este microserviço, avaliado
assincronamente por todas as camadas (incluindo XGBoost nos `deny` do HBOS). Custo de risco
zero. Reproduzível (semente derivada de `transaction_id`). `shadow_mode: true` no contrato
de evento, filtrado pela fila operacional.

Amostra de exploração controlada (opcional): teto de perda em R$ aprovado, fração pequena
na faixa baixo-intermediário onde a política sempre nega.

## Qualidade de dados

Controles contínuos com alerta: nulos, duplicidades, replays, estornos, timestamps
inválidos/futuros, valores fora de faixa, geo inválida, mudança de schema, proporção de CPF
novo, cobertura por canal, leakage temporal.

**Nulos em features críticas > 2% bloqueiam promoção.**

Falha de qualidade acima do limite **bloqueia o pipeline de treino**, não só alerta.

## Validação temporal

```text
Treino:     passado
Validação:  período intermediário
Teste:      período mais recente
```

Split aleatório é proibido para performance. Instante de disponibilidade de cada feature
documentado no registry — hoje `unreconciled` ([features.md](../contratos/features.md)).

## Taxonomia de rótulos

```text
fraude_confirmada
fraude_suspeita
em_disputa
legitima_confirmada
sem_desfecho
```

- Corte de treino respeita a janela de maturação medida na Etapa 2 do MAPA.
- Negação explícita no step-up ≠ não-resposta.
- Hard rule como pseudo-rótulo só como hipótese, contra baseline (circularidade com NEG83).

Ausência relatada de fraude confirmada em seis meses: não concluir inviabilidade de retreino
antes da auditoria de fontes (MAPA Etapa 2).

## Drift

| Indicador | Limiar | Ação |
|---|---|---|
| PSI | < 0,10 | estável |
| PSI | 0,10–0,25 | alerta; revisão em **7 dias** |
| PSI | > 0,25 | drift crítico; retreino |
| KS | p-valor < 0,01 | alerta de mudança de distribuição |

Mais: distribuição de escores, nulos, volume, ticket, horários, parcelas, canais,
estabelecimentos, regiões, dispositivos, taxa de CPF novo, fraude confirmada por banda,
divergência HBOS/XGB.

## Viés e equidade

Coortes mínimas: tempo de relacionamento, canal, região, tipo de estabelecimento.

Por segmento: FPR, FNR, recall, taxa de challenge, taxa de deny.

Mitigar viés de regras históricas e assimetria de massa de treino. Sinais correlacionados
(geo em regra + HBOS + XGBoost) não devem ser contados três vezes sem limite na política.

Peso do HBOS reduzido em cold start ([ADR-0003](../adr/0003-politica-de-cold-start.md)).

## AutoML (offline)

Permitido: exploração, comparação, SHAP, challenger em shadow **≥ 4 semanas**, canário.

Vedado: `transação online → chamada remota Azure AutoML → decisão`.

- Classificação: `primary_metric: average_precision_score_weighted`, split temporal estrito.
- Regressão: `primary_metric: normalized_root_mean_squared_error`, calibração por faixas.
- `blocked_models`: inferência p95 > **15 ms**.

Acurácia não promove modelo. Conjunto mínimo:

| Categoria | Métricas |
|---|---|
| Discriminação | PR-AUC / AP ponderada, ROC-AUC (cautela), recall, precisão |
| Erro | FPR, FNR |
| Operação | taxa de challenge, aprovação legítima, custo |
| Confiabilidade | calibração (se houver desfechos), estabilidade |
| Negócio | custo evitado, fraude residual |
| Sistema | latência p95, inclusive 15 ms de inferência |
| Equidade | FPR/FNR/recall/challenge/deny por coorte |
| Governança | explicabilidade, `model_version`, schema de features |

## Rollout

```text
Dados validados → treino offline → validação temporal
→ avaliação (performance, custo, viés) → registry
→ shadow ≥ 4 semanas → canário → monitoramento
→ champion ou rollback < 10 min
```

Estados: `candidate`, `challenger`, `champion`, `deprecated`, `rolled_back`
([ADR-0004](../adr/0004-publicacao-de-modelos-e-cache.md)).

## Critérios de aceite

- Shadow 1%–5% ativo, cobrindo transações com e sem short-circuit de HBOS.
- Pipeline bloqueado se nulos críticos > 2% ou PSI > 0,25 sem revisão.
- Zero avaliação por split aleatório.
- Zero `sem_desfecho` como negativa (teste do pipeline).
- Janela de maturação documentada em dias e aplicada ao corte.
- Métricas por coorte em toda promoção.
- Promoção bloqueada se faltar métrica do conjunto mínimo.
- AutoML sem chamada no fast path (teste de contrato).
- Challenger ≥ 4 semanas em shadow antes do canário.
- Rollback exercitado < 10 min.
