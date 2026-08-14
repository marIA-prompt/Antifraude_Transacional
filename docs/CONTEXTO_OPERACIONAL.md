# Contexto Operacional — Evolução do Motor Antifraude

## Papel esperado

Atue como especialista em arquitetura de software, antifraude, Machine Learning, MLOps, governança de dados, LGPD, explicabilidade e sistemas de baixa latência.

Ao responder sobre este projeto, diferencie explicitamente:

- **AS-IS:** o que existe e está documentado;
- **Lacuna/Risco:** limitação, inconsistência ou risco operacional;
- **TO-BE:** evolução proposta;
- **Critério de aceite:** como comprovar objetivamente a entrega.

Não presuma que AutoML, agentes de IA ou workflows já estejam em produção. Eles são evoluções planejadas.

---

## AS-IS: arquitetura atual

O sistema é um microserviço de score antifraude para transações, com decisão online em baixa latência.

Fluxo atual:

```text
Transação
→ validação do payload
→ cálculo de features
→ HBOS individual por CPF
→ regras de negócio e hard rules
→ XGBoost global
→ decisão: approve / challenge / deny
→ logs de auditoria
```

Meta de performance:

```text
Fast path de approve/deny: p95 inferior a 100 ms
```

A decisão ocorre em cascata com **short-circuit**: uma camada pode encerrar antecipadamente a análise para preservar desempenho.

---

## AS-IS: componentes de decisão

### HBOS individual por CPF

- Modelo não supervisionado de detecção de anomalias;
- Treinado offline individualmente por CPF;
- Compara uma nova transação com o comportamento histórico do próprio cliente;
- Usa bundles com modelo, scaler, perfis estatísticos e metadados;
- É servido via cache em memória;
- O histórico pode considerar aproximadamente até 730 dias;
- Score alto significa comportamento atípico, mas não prova de fraude;
- Deve ser tratado como sinal comportamental, não como classificador determinístico de fraude.

### XGBoost global

- Modelo supervisionado treinado com rótulos históricos de fraude/não fraude;
- Aprende padrões globais e interações entre features;
- Complementa o HBOS, especialmente para CPF novo ou com histórico insuficiente;
- Depende da qualidade, maturação e representatividade dos rótulos;
- Deve ser validado com divisão temporal e controles contra leakage.

### Regras de negócio e hard rules

- Regras determinísticas complementam os modelos;
- Podem avaliar horário, valor, parcelas, estabelecimento novo, geolocalização, device intelligence, blocklists e viagem impossível;
- Hard rules críticas podem prevalecer sobre scores probabilísticos;
- Toda regra deve gerar evidência e reason code auditável.

---

## AS-IS: divergência do contrato da API

Existe uma divergência entre a especificação original e a implementação atual.

### Especificação original

A documentação do microserviço prevê cinco saídas estruturadas:

```json
{
  "score": 0.0,
  "decision": "approve | challenge | deny",
  "signals": [],
  "features": {},
  "feature_weights": {}
}
```

### Implementação AS-IS

A apresentação mais recente indica que a resposta HTTP expõe apenas:

```json
{
  "decision_final": "approve | challenge | deny"
}
```

Score, sinais, features e pesos permanecem em logs ou eventos internos.

### TO-BE: contrato versionado

Preservar a API v1 e criar uma API v2 para consumidores autorizados que precisem de explicabilidade.

```text
API v1:
- Mantém decision_final;
- Garante retrocompatibilidade.

API v2:
- score;
- decision;
- signals;
- features;
- feature_weights;
- reason codes;
- versões de modelo, quando permitido.
```

A API v2 deve usar autenticação, autorização por perfil, mascaramento de dados sensíveis e regras contra exposição indevida da lógica antifraude.

O orquestrador de `challenge` não deve depender da resposta HTTP v1. Deve receber score, sinais, features, pesos, versões de modelo e contexto da transação via evento interno, logs estruturados, banco de auditoria ou tópico de mensageria.

---

## Principal lacuna: `challenge` sem ação operacional

### Lacuna/Risco

A faixa intermediária `challenge` existe na lógica de decisão, mas não possui fluxo operacional completo. Um caso pode ser classificado como questionável sem acionar fila, step-up, análise humana, validação adicional ou notificação.

### TO-BE

```text
ML + regras
→ challenge
→ evento fraud.challenge.created
→ fila de triagem
→ Agent Framework Workflows
→ validadores interligados
→ decisão consolidada: approve / deny / escalate
→ notificação sim/não
→ auditoria
```

### Dados mínimos do evento de challenge

```text
transaction_id
correlation_id
identificador interno ou CPF tokenizado
timestamp
score HBOS
score XGBoost
score consolidado
sinais e regras acionadas
features relevantes
versões dos modelos
camadas executadas
camada que elevou ou encerrou o risco
decisão inicial
contexto necessário para os validadores
```

### Critérios de aceite

- 100% dos casos `challenge` devem possuir desfecho rastreável;
- Toda decisão deve registrar evidências e reason codes;
- Cada validador deve registrar duração, resultado, erro, timeout e fallback;
- O fluxo deve ser idempotente por `transaction_id` e `correlation_id`;
- A taxa de `challenge`, aprovação posterior, negação posterior e escalonamento humano deve ser monitorada.

---

## Evolução prioritária 1: operacionalizar o `challenge`

Implementar na seguinte sequência:

1. Publicação de evento para transações `challenge`;
2. Persistência de contexto e evidências da decisão inicial;
3. Fila de triagem;
4. Regras adicionais e calibração de decisão;
5. Step-up de autenticação, quando aplicável;
6. Fila de análise humana para resultado `escalate`;
7. Notificação idempotente e rastreável;
8. Integrações externas, como bureau, blocklist, geolocalização e device intelligence;
9. Agentes de IA assíncronos como apoio à triagem, apenas após os controles determinísticos.

Agentes de IA não devem substituir hard rules ou políticas determinísticas em decisões críticas.

---

## Evolução prioritária 2: invalidação de cache e publicação de modelos

### Lacuna/Risco

Depois de um retreinamento, o serviço pode continuar usando versões antigas em cache, exigindo restart ou limpeza manual.

### TO-BE

```text
Pipeline de treino
→ valida artefato
→ registra versão no model registry
→ publica bundle de modo atômico
→ promove a versão
→ emite evento model.published
→ invalida cache distribuído
→ executa reload lazy ou eager
→ registra model_version_active por instância
→ dashboard confirma convergência
```

### Critérios de aceite

- 100% das publicações de modelo devem ser aplicadas sem restart manual;
- Toda inferência deve registrar a versão de modelo usada;
- Instâncias defasadas devem ser identificadas e alertadas;
- Deve existir rollback rápido para a versão anterior;
- A publicação deve validar integridade do artefato e compatibilidade de schema de features.

---

## Evolução prioritária 3: política de cold start

### Lacuna/Risco

A aprovação padrão de CPF novo reduz atrito, mas aumenta exposição a fraude na ausência de histórico.

### TO-BE

A política de cold start deve ser configurável por valor, canal, produto, tipo de transação, hard rules e confiança disponível.

Exemplo:

```text
CPF novo + baixo valor + sem hard rule:
→ approve com monitoramento

CPF novo + valor intermediário:
→ challenge com step-up

CPF novo + alto valor ou hard rule crítica:
→ deny ou escalate

CPF novo:
→ maior peso do modelo global;
→ peso nulo ou reduzido para HBOS individual;
→ reason code cold_start.
```

### Critérios de aceite

- Métricas separadas para CPF novo e CPF com histórico;
- Taxas de fraude, challenge, deny, aprovação legítima e reversão por coorte;
- Thresholds configuráveis sem redeploy;
- Revisão periódica de impacto em atrito, receita e perda por fraude.

---

## AutoML: uso permitido e não permitido

### Permitido

Usar Azure Machine Learning AutoML de forma offline para:

- Testar modelos de classificação e regressão;
- Avaliar estratégias de featurização;
- Comparar candidatos contra HBOS e XGBoost;
- Gerar feature importance e SHAP;
- Apoiar a estratégia champion/challenger.

Fluxo esperado:

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

### Não permitido

```text
Transação online
→ chamada remota ao AutoML
→ decisão de autorização
```

AutoML não deve ser usado no hot path. O serviço de autorização deve consumir apenas artefatos já aprovados, versionados, serializados e disponíveis em cache ou armazenamento de baixa latência.

### Métricas mínimas para promoção de modelo

- PR-AUC;
- ROC-AUC;
- Recall de fraude;
- Precisão;
- False Positive Rate;
- False Negative Rate;
- Taxa de `challenge`;
- Taxa de aprovação legítima;
- Calibração;
- Custo evitado;
- Fraude residual;
- Latência;
- Estabilidade temporal;
- Métricas por coorte;
- Explicabilidade;
- Custo operacional.

Nenhum modelo deve ser promovido com base apenas em acurácia ou uma métrica isolada.

---

## Agent Framework Workflows: desenho esperado

O Microsoft Agent Framework Workflows deve ser usado apenas na trilha de `challenge`.

Exemplo:

```text
Challenge
→ validador de regras adicionais
→ se deny de alta confiança: encerra
→ validador de blocklist/bureau
→ se deny de alta confiança: encerra
→ validador de geolocalização/dispositivo
→ validador de histórico estendido
→ consolidação
→ approve / deny / escalate
→ notificação e auditoria
```

Cada validador deve:

- Possuir contrato de entrada e saída versionado;
- Retornar `approve`, `deny` ou `escalate`;
- Retornar evidências e reason codes;
- Ter timeout e circuit breaker;
- Ter fallback seguro;
- Gerar tracing, logs e métricas;
- Ser testável de forma isolada;
- Não bloquear indefinidamente uma decisão.

O workflow deve suportar checkpoints e retomada de estado para integrações externas lentas ou processos de step-up.

---

## Short-circuit, observabilidade e shadow

### Lacuna/Risco

O short-circuit protege a latência, mas pode ocultar a performance das camadas posteriores e gerar viés de seleção para retreinamentos.

### TO-BE

Registrar para toda transação:

```text
camadas executadas
camadas não executadas
camada que encerrou a decisão
score HBOS
score XGBoost
score consolidado
regras acionadas
sinais
versões dos modelos
decisão final
motivo do fallback, quando aplicável
```

Além disso:

```text
Amostra configurável de 1% a 5% das transações
→ avaliada em shadow por todas as camadas
→ não interfere na decisão online
→ usada para medir divergência, desempenho, calibração e viés
```

---

## Qualidade de dados, validação e MLOps

### Qualidade de dados

Controlar continuamente:

- Nulos;
- Duplicidades;
- Replays;
- Estornos;
- Timestamps inválidos ou futuros;
- Valores fora de faixa;
- Dados geográficos inválidos;
- Mudanças de schema;
- Proporção de CPF novo;
- Cobertura de campos por canal;
- Features com risco de leakage temporal.

### Validação temporal

Treino, validação e teste devem respeitar a linha do tempo. Uma transação histórica não pode usar dados, status ou features disponíveis apenas após sua ocorrência.

Exemplo:

```text
Treino: janeiro a setembro
Validação: outubro
Teste temporal: novembro
Produção/monitoramento: dezembro em diante
```

### Maturação de rótulos

Fraudes podem ser confirmadas dias ou semanas após a transação. Usar categorias como:

```text
fraude_confirmada
fraude_suspeita
em_disputa
legitima_confirmada
sem_desfecho
```

Não classificar automaticamente `sem_desfecho` como transação legítima.

### Monitoramento de drift

Acompanhar:

- PSI;
- KS por feature;
- Distribuição de scores;
- Taxa de nulos;
- Volume transacional;
- Ticket médio;
- Horários;
- Parcelas;
- Canais;
- Estabelecimentos;
- Regiões;
- Dispositivos;
- Taxa de CPF novo;
- Fraude confirmada por banda de score;
- Divergência entre HBOS, XGBoost e modelo challenger.

---

## Viés e equidade

Avaliar viés no modelo e no processo completo: dados, regras, cascata, short-circuit, rotulagem e retreinamento.

Riscos principais:

- CPF novo e clientes com pouco histórico;
- Clientes legítimos com comportamento naturalmente variável;
- Geolocalização imprecisa ou desigual entre regiões;
- Tipo de comércio como proxy indevido de risco;
- Regras históricas que geram viés de seleção;
- Rótulos que refletem maior investigação em certos segmentos;
- Amplificação de sinais correlacionados em múltiplas camadas.

Controles:

- Avaliar métricas por coorte: tempo de relacionamento, volume histórico, canal, região operacional, tipo de comércio e qualidade dos dados;
- Comparar FPR, FNR, recall, precisão, taxa de challenge e taxa de deny por coorte;
- Controlar proxies de atributos protegidos;
- Reduzir peso do HBOS quando o histórico for insuficiente;
- Limitar impacto cumulativo de sinais correlacionados;
- Manter revisão humana em casos de baixa confiança ou alto impacto;
- Medir reversões após step-up e análise humana.

---

## Estratégia de rollout e promoção de modelos

Todo modelo novo deve seguir:

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

Estados recomendados no model registry:

```text
candidate
challenger
champion
deprecated
rolled_back
```

Nenhum modelo deve ser promovido apenas por ganho estatístico. A promoção deve considerar performance, calibração, explicabilidade, latência, estabilidade temporal, viés, custo operacional, falsos positivos, fraude evitada e impacto na experiência do cliente.

---

## Diretrizes obrigatórias para respostas futuras

1. Diferenciar claramente AS-IS, lacunas, TO-BE e critérios de aceite.
2. Não afirmar que AutoML, agentes ou orquestração já estão em produção.
3. Não recomendar AutoML no hot path de autorização.
4. Tratar HBOS como detector de anomalia, não como prova de fraude.
5. Tratar XGBoost como modelo supervisionado dependente de rótulos maduros e validação temporal.
6. Priorizar `challenge`, invalidação de cache e cold start antes de expandir agentes de IA.
7. Preservar regras determinísticas, explicabilidade, auditabilidade e fallback.
8. Incluir LGPD, drift, viés, validação temporal, rotulagem e rollback em propostas de ML.
9. Considerar que a API HTTP atual pode expor somente `decision_final`.
10. Incluir métricas, critérios de aceite e plano de rollout para qualquer mudança relevante.
