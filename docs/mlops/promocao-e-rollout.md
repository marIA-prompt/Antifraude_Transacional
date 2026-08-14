# AutoML, promoção de modelos e rollout

Endereça `LR-16`. Define o que AutoML pode e não pode fazer, e o que é exigido para promover
qualquer modelo.

## 1. AutoML — uso permitido

Azure Machine Learning AutoML é permitido **offline**, para:

- testar modelos de classificação e regressão;
- avaliar estratégias de featurização;
- comparar candidatos contra HBOS e XGBoost;
- gerar feature importance e SHAP;
- apoiar a estratégia champion/challenger.

```text
Dados históricos maduros
→ validação de qualidade
→ split temporal
→ AutoML offline
→ avaliação técnica, de negócio e de viés
→ candidate
→ challenger em shadow
→ rollout canário
→ champion ou rollback
```

Pré-condições, herdadas de [dados e validação temporal](dados-e-validacao-temporal.md): rótulos
maduros, split temporal, controle de leakage e verificações de qualidade aprovadas. AutoML sobre
dados com leakage produz um campeão espetacular offline e inútil online — e a featurização
automática é justamente onde o leakage entra sem ser notado.

## 2. AutoML — uso não permitido

```text
Transação online
→ chamada remota ao AutoML
→ decisão de autorização
```

AutoML **não** entra no hot path. O serviço de autorização consome apenas artefatos já aprovados,
versionados, serializados e disponíveis em cache ou armazenamento de baixa latência.

Motivos, todos verificáveis: chamada remota não cabe no orçamento de p95 < 100 ms; cria dependência
externa no caminho crítico de autorização; a versão que decidiu deixa de ser controlada pelo
serviço, quebrando reprodutibilidade e auditoria; e não há rollback local quando o endpoint remoto
muda de comportamento.

O mesmo raciocínio vale para agentes de IA: apoio assíncrono na trilha de `challenge`, nunca
componente do hot path nem substituto de hard rule ou política determinística.

## 3. Métricas mínimas para promoção

Nenhum modelo é promovido com base apenas em acurácia ou em uma métrica isolada. Em fraude, a classe
positiva é rara: um modelo que aprova tudo tem acurácia altíssima e valor negativo.

| Métrica | Por que entra na decisão |
| --- | --- |
| PR-AUC | Métrica principal sob classe desbalanceada |
| ROC-AUC | Comparabilidade e separabilidade geral |
| Recall de fraude | Fraude capturada |
| Precisão | Custo de investigar e de negar indevidamente |
| False Positive Rate | Atrito imposto a cliente legítimo |
| False Negative Rate | Perda absorvida |
| Taxa de `challenge` | Capacidade operacional necessária (fila, step-up, humano) |
| Taxa de aprovação legítima | Impacto comercial |
| Calibração | Score precisa significar probabilidade para sustentar threshold e faixa |
| Custo evitado | Efeito financeiro da captura |
| Fraude residual | O que passa depois de toda a cascata |
| Latência | Viabilidade no hot path |
| Estabilidade temporal | Performance consistente ao longo dos meses, não só no teste |
| Métricas por coorte | Detecção de viés (ver [viés e equidade](vies-e-equidade.md)) |
| Explicabilidade | Reason code defensável em contestação e auditoria |
| Custo operacional | Treino, serving, armazenamento e cardinalidade de bundles |

A promoção considera o conjunto: performance, calibração, explicabilidade, latência, estabilidade
temporal, viés, custo operacional, falsos positivos, fraude evitada e impacto na experiência do
cliente. Ganho estatístico isolado não promove.

**Regra de decisão explícita.** Antes de comparar candidatos, declarar: qual é a métrica principal,
quais são as restrições invioláveis (por exemplo, FPR máximo por coorte, taxa de `challenge` máxima
compatível com a capacidade operacional, p95 de latência) e qual o ganho mínimo relevante. Sem isso,
a comparação vira escolha da métrica que favorece o candidato preferido.

## 4. Estados no model registry

```text
candidate
challenger
champion
deprecated
rolled_back
```

| Estado | Significado | Efeito em produção |
| --- | --- | --- |
| `candidate` | treinado e avaliado offline | nenhum |
| `challenger` | avaliado em shadow contra o champion | scoring paralelo, sem decidir |
| `champion` | versão que decide | ativo no hot path |
| `deprecated` | substituído, mantido para auditoria | nenhum |
| `rolled_back` | revertido após problema em produção | bloqueado para nova promoção sem análise |

`rolled_back` é estado distinto de `deprecated` de propósito: perder a informação de que uma versão
falhou em produção convida a repetir a falha.

## 5. Rollout

```text
Dados validados
→ treino offline
→ validação temporal
→ avaliação de performance, custo e viés
→ registro do modelo
→ shadow mode
→ rollout canário
→ monitoramento
→ promoção a champion ou rollback
```

| Fase | Critério de entrada | Critério de saída |
| --- | --- | --- |
| Shadow | artefato registrado, schema compatível | performance e calibração medidas na população completa; sem regressão por coorte |
| Canário | shadow aprovado, rollback exercitado | métricas dentro do previsto na fatia canário, sem alerta de viés |
| Expansão | canário estável na janela definida | convergência de versão em todas as instâncias |
| Champion | expansão completa | monitoramento contínuo ativo |

O rollout depende operacionalmente da [Evolução 2](../evolucoes/02-publicacao-de-modelos-e-cache.md):
sem publicação atômica, versão registrada por inferência e invalidação de cache, "canário" e
"rollback" não são executáveis de forma confiável.

**Gatilhos de rollback**, definidos antes do rollout e não durante o incidente: queda de recall além
do limite, salto de FPR, degradação de calibração, aumento de taxa de `challenge` acima da capacidade
operacional, regressão em qualquer coorte protegida, estouro de latência ou divergência
champion/challenger fora do esperado.

## Critérios de aceite

| # | Critério | Como comprovar |
| --- | --- | --- |
| CA-P.1 | Nenhuma chamada a AutoML no hot path | Revisão de dependências e de tráfego de saída do serviço de autorização; teste de rede confirma ausência de chamada externa a endpoint de AutoML |
| CA-P.2 | Toda promoção registra o conjunto completo de métricas | Ficha de promoção com todas as métricas da seção 3 preenchidas, incluindo por coorte |
| CA-P.3 | Regra de decisão declarada antes da comparação | Documento de avaliação versionado antes do resultado, com métrica principal, restrições e ganho mínimo |
| CA-P.4 | Todo modelo passa por shadow antes de canário | Registro de estados no registry, sem transição direta `candidate` → `champion` |
| CA-P.5 | Gatilhos de rollback definidos e armados | Alertas configurados correspondentes a cada gatilho, com runbook |
| CA-P.6 | Rollback exercitado | Evidência de rollback executado em ambiente controlado antes da promoção |
| CA-P.7 | Artefato de produção é local e versionado | Inferência registra `model_version`; artefato servido de cache/armazenamento de baixa latência |
