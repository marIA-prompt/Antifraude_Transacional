# Governança de dados, MLOps, AutoML, viés e LGPD

Este documento consolida as diretrizes do contexto operacional que **não** têm implementação
de código neste repositório (pipelines de treino, AutoML, drift, viés), deixando explícito o
que é AS-IS/TO-BE e o que é apenas orientação de processo.

## AutoML: uso permitido e não permitido

- **Permitido**: uso *offline* do Azure Machine Learning AutoML para testar modelos, comparar
  candidatos contra HBOS/XGBoost, gerar feature importance/SHAP e apoiar champion/challenger.
- **Não permitido**: qualquer chamada do hot path de autorização a um serviço de AutoML.
  `StubXgboostScorer` (`src/antifraud/models_ml/xgboost_model.py`) ilustra o contrato correto:
  o serviço de autorização consome apenas artefatos já aprovados, versionados e disponíveis em
  cache/armazenamento de baixa latência — nunca uma chamada remota síncrona a um serviço de
  treinamento/AutoML.
- **Nenhum AutoML, agente de IA ou orquestração está em produção neste repositório.** Todos os
  componentes de ML aqui são interfaces com stubs determinísticos para exercitar a cascata de
  decisão e os testes automatizados.

### Métricas mínimas para promoção de modelo (processo, não implementado em código)

PR-AUC, ROC-AUC, recall de fraude, precisão, FPR, FNR, taxa de `challenge`, taxa de aprovação
legítima, calibração, custo evitado, fraude residual, latência, estabilidade temporal,
métricas por coorte, explicabilidade, custo operacional. Nenhum modelo deve ser promovido com
base apenas em acurácia ou uma métrica isolada. O `ModelRegistry` (ver `MODEL_LIFECYCLE.md`)
fornece os estados (`candidate`/`challenger`/`champion`/`deprecated`/`rolled_back`) que
sustentariam esse processo, mas o cálculo e a checagem automática dessas métricas antes da
promoção são lacuna aberta.

## Qualidade de dados e validação temporal

Controles descritos no contexto operacional (nulos, duplicidades, replays, estornos,
timestamps inválidos/futuros, valores fora de faixa, dados geográficos inválidos, mudanças de
schema, proporção de CPF novo, cobertura de campos por canal, leakage temporal) são
parcialmente cobertos no hot path por `antifraud.validation.payload.validate_payload`
(timestamp futuro, geolocalização fora de faixa, campos obrigatórios). A validação completa de
qualidade de dados para treino/monitoramento contínuo é um pipeline offline fora de escopo
deste repositório.

Treino/validação/teste devem respeitar a linha do tempo (nenhuma feature ou rótulo disponível
apenas após a transação pode ser usado retroativamente). Nenhum código de treino existe aqui —
esta é uma diretriz de processo para quando o pipeline de treino for implementado.

## Maturação de rótulos

Categorias recomendadas: `fraude_confirmada`, `fraude_suspeita`, `em_disputa`,
`legitima_confirmada`, `sem_desfecho`. `LabelMaturity`
(`src/antifraud/domain/enums.py`) apenas declara essas categorias como um contrato de domínio
reutilizável por um futuro pipeline de rotulagem — **não há pipeline de rotulagem
implementado**. Nunca classificar `sem_desfecho` como transação legítima.

## Monitoramento de drift

PSI, KS por feature, distribuição de scores, taxa de nulos, volume, ticket médio, horários,
parcelas, canais, estabelecimentos, regiões, dispositivos, taxa de CPF novo, fraude confirmada
por banda de score, divergência entre HBOS/XGBoost/challenger. **Nenhum monitoramento de drift
está implementado neste repositório.** O `DecisionTrace` produzido a cada transação contém os
dados brutos necessários (scores, features, decisão, camada de encerramento) para alimentar
esse monitoramento em um pipeline externo.

## Viés e equidade

Riscos e controles descritos no contexto operacional (CPF novo, geolocalização imprecisa,
tipo de comércio como proxy, rótulos enviesados por investigação desigual, amplificação de
sinais correlacionados) devem ser avaliados por coorte (tempo de relacionamento, volume
histórico, canal, região, tipo de comércio, qualidade dos dados). A `ColdStartPolicy`
(ver `COLD_START.md`) implementa um dos controles recomendados — reduzir o peso do HBOS
quando o histórico é insuficiente — mas a avaliação de viés em si (comparação de FPR/FNR/
recall/precisão/taxa de challenge/taxa de deny por coorte) não está implementada; requer um
pipeline de avaliação offline com acesso a dados históricos rotulados.

## LGPD e minimização de dados

- CPF é tokenizado (`antifraud.challenge.events.tokenize_cpf`) antes de sair do processo em
  qualquer evento interno (`fraud.challenge.created`); nunca é persistido em claro no
  `DecisionTrace`.
- A API v2 mascara `features`/`feature_weights`/`model_versions`/`rule_evidences` para
  consumidores com perfil `basic`, reduzindo exposição da lógica antifraude e de dados
  potencialmente sensíveis a quem não tem necessidade de acesso completo.
- Um DPO/time de privacidade deve revisar quais features podem conter dados pessoais
  sensíveis (ex.: geolocalização) antes de expandir o que é exposto via API v2 ou enviado a
  qualquer integração externa (bureau, blocklist) — isso é uma responsabilidade de governança,
  não algo que o código sozinho garante.

## Diretriz de sequenciamento

Conforme o contexto operacional: priorizar `challenge` (Evolução prioritária 1), invalidação
de cache (Evolução prioritária 2) e cold start (Evolução prioritária 3) **antes** de expandir
AutoML ou agentes de IA. Este repositório segue essa ordem: as três evoluções prioritárias têm
implementação de código; AutoML e agentes de IA são documentados apenas como diretrizes de
processo, sem qualquer implementação, para não sugerir que já estejam em produção.
