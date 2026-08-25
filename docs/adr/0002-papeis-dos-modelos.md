# ADR-0002 — Papéis dos modelos: HBOS, XGBoost, regras e o que fica fora do hot path

- **Status:** aceito (revisado em 2026-08-25)
- **Depende de:** [ADR-0001](0001-topologia-de-decisao.md)
- **Lacunas endereçadas:** L4 (short-circuit), L7 (rótulos), L8 (NEG83 / Motor H)

## Contexto

### AS-IS

Os modelos existentes são adequados ao problema. O que precisa ficar explícito é o **papel**
de cada um, o que cada um **não** é, e o que é vedado no caminho de autorização.

### Lacuna/Risco

- Interpretar HBOS `deny` como prova de fraude.
- Treinar ou promover XGBoost com `sem_desfecho` como negativa, ou sem split temporal.
- Colocar AutoML, Motor H ou agentes de IA no hot path.
- Afirmar quantidade de features (10 ou 13) como definitiva ([D-2](../arquitetura/divergencias-documentais.md)).

## Decisão: inventário e papéis

### Regras determinísticas e hard rules — soberanas onde a política exige certeza

Viagem impossível e demais vetos críticos prevalecem sobre scores. Toda regra produz
evidência e reason code. Nenhum modelo — e nenhum agente de IA — sobrepõe uma hard rule
crítica.

### HBOS individual por CPF — detector de anomalia, não prova de fraude

Mantido. É a escolha correta para o papel:

- treino offline por cliente, janela de até ~730 dias;
- valor imediato mesmo com rótulo atrasado — **esta é a razão de existir do HBOS**;
- inferência a partir de bundle em cache (budget: 8 ms hit + 12 ms HBOS/regras);
- explicabilidade nativa por histograma, sem SHAP em tempo real.

Restrições:

- score alto = comportamento atípico;
- no AS-IS, `HBOS = deny` é terminal (ADR-0001). Isso **não** autoriza redigir reason codes
  como "fraude confirmada pelo HBOS";
- peso cai a zero ou é reduzido em cold start ([ADR-0003](0003-politica-de-cold-start.md)).

### XGBoost global — segunda linha supervisionada, fail-safe da cascata

Mantido. Treinado com **fraude confirmada**. Cobre CPF novo e padrões em escala. Depende
integralmente da qualidade e maturação dos rótulos.

Não é ponto único de falha: se indisponível, a decisão do HBOS + regras permanece
(`xgb_unavailable`).

Challengers (LightGBM ou candidato de AutoML offline) só entram por champion/challenger,
shadow ≥ 4 semanas, canário e rollback < 10 min. Nenhum challenger no hot path sem passar
pelo budget de **15 ms p95** de inferência (`blocked_models` caso exceda).

### Consolidação dual

AS-IS: média ponderada entre HBOS (quando executado) e XGBoost (quando executado), com
regras. TO-BE: pesos configuráveis por confiança de histórico (ADR-0003), versionados, sem
redeploy. Meta-modelo de stacking **rejeitado** nesta fase: perde a camada decisora
auditável. Se um combinador aprendido for necessário depois do diagnóstico do MAPA, a forma
aceita é regressão logística sobre poucos sinais, com coeficientes publicados em
`feature_weights`.

### Calibração

XGBoost devolve escore, não probabilidade calibrada. Sem calibração versionada, os
thresholds de `challenge` (`approve_max`) e `deny` (`deny_min`) derivam a cada retreino e a
fila absorve o efeito. Calibração isotônica ou Platt entra como artefato publicado junto ao
modelo ([ADR-0004](0004-publicacao-de-modelos-e-cache.md)), depois do protocolo de avaliação
do [MAPA Etapa 6](../mlops/acompanhamento-modelagem.md) — e só se houver desfechos
observados em quantidade suficiente. Não apresentar calibração como concluída sem essa base.

### Motor H — fora deste inventário de autorização

Motor H é ranking de recuperação de jornadas NEG83 (`later_success_score`), com 33 features
de `FIRST_NEG83`, target distinto de fraude confirmada. **Não é camada deste microserviço.**
Ver [motor-h-neg83.md](../recuperacao/motor-h-neg83.md) e D-3.

## O que fica fora do hot path

| Componente | Onde pode ser usado | Por quê |
|---|---|---|
| Azure AutoML | Offline: candidatos, SHAP, champion/challenger, shadow ≥ 4 semanas | Chamada remota em autorização é vedada; consome o p95 |
| Agent Framework Workflows e agentes de IA | Somente trilha assíncrona de `challenge` | Nunca substituem hard rules |
| Motor H / HGB de recuperação | Teste assistido da policy NEG83, fora da autorização | Target `LATER_SUCCESS`, não fraude; 33 features distintas |
| Bureau, device intelligence, geo enriquecida | Validadores da trilha de challenge (timeout 800 ms interno / 2 s externo) | Dependência externa proibida no fast path |
| Modelos de sequência / autoencoder global | Shadow ou validador assíncrono | Latência e instabilidade incompatíveis com 15 ms |

### AutoML — configuração de referência (offline)

- Classificação: `primary_metric: average_precision_score_weighted`, split temporal estrito.
- Regressão: `primary_metric: normalized_root_mean_squared_error`, calibração por faixas.
- `blocked_models`: qualquer candidato com inferência p95 > 15 ms.

## Critérios de aceite

- Reason codes de HBOS redigidos como anomalia/atipicidade em 100% dos casos; auditoria
  amostral sem ocorrência de "fraude confirmada pelo HBOS".
- 100% das inferências com `model_version` (HBOS bundle e/ou XGBoost) registrada.
- Nenhum artefato promovido com métrica isolada; conjunto em
  [MLOps](../mlops/dados-rotulos-e-promocao.md).
- AutoML sem chamada no span de autorização, verificado por teste de contrato.
- Challenger em shadow ≥ 4 semanas com PR-AUC (ou AP ponderada) e FPR/FNR por coorte antes
  de canário.
- Lista canônica de features **não** é critério deste ADR enquanto D-2 estiver aberto —
  pertence ao [registry](../contratos/features.md).
