# Observabilidade do short-circuit e avaliação em shadow

Endereça `LR-04` e `LR-11`. É pré-requisito das três evoluções prioritárias: sem trace por camada,
nenhum critério de aceite delas é verificável.

## AS-IS

- A cascata usa short-circuit: uma camada pode encerrar a análise antecipadamente.
- Há logs de auditoria da decisão.
- Não há registro estruturado e garantido de quais camadas executaram, quais foram suprimidas e qual
  encerrou a decisão.

## Lacuna / Risco

O short-circuit protege a latência e é para permanecer. O problema é o efeito colateral sobre
medição e aprendizado:

- **Performance invisível das camadas posteriores.** Se a hard rule nega antes do XGBoost, não existe
  score do XGBoost para aquele caso. Não é possível dizer se o modelo teria concordado, nem medir o
  ganho marginal de cada camada.
- **Viés de seleção no retreinamento.** O modelo é treinado sobre a população que chegou até ele —
  filtrada pela regra 83 e pelas camadas anteriores. Ele aprende a discriminar dentro de um recorte,
  e sua métrica offline não descreve a população real.
- **Atribuição impossível.** Sem camada terminal registrada, "por que essa transação foi negada" tem
  resposta apenas por reconstrução manual, o que não escala para contestação e auditoria.

## TO-BE

### Decision trace: um registro por transação

Campos obrigatórios, sempre, inclusive em `approve`
([schema](../contratos/schemas/decision-trace.schema.json)):

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

Complementos que tornam o trace utilizável em produção: `transaction_id`, `correlation_id`,
`policy_version`, nível de confiança do histórico, duração por camada e indicador de amostra em
shadow. Score de camada não executada é `null` — nunca `0`, que é um valor de score válido e
corromperia qualquer agregação.

O trace é assíncrono em relação à resposta: escrita enfileirada com métrica de descarte. Perder trace
é ruim; estourar o p95 de autorização é pior. A perda precisa ser visível, não presumida como zero.

### Amostra em shadow

```text
Amostra configurável de 1% a 5% das transações
→ avaliada em shadow por todas as camadas
→ não interfere na decisão online
→ usada para medir divergência, desempenho, calibração e viés
```

Regras de desenho:

- **Amostragem determinística** por hash de `transaction_id`, de modo que a inclusão seja
  reproduzível e a taxa seja ajustável sem redeploy.
- **Amostra sem filtro de camada anterior**: precisa incluir casos que o short-circuit teria
  encerrado, inclusive os negados por hard rule. É justamente esse recorte que hoje é invisível.
- **Execução fora do caminho de resposta**, para não consumir o orçamento de latência. Se o custo em
  hot path for inevitável para alguma camada, ela roda em replay assíncrono a partir das features já
  calculadas e registradas.
- **Isolamento de efeito**: resultado de shadow nunca altera a decisão, nunca dispara notificação e
  nunca aciona integração externa que gere custo por consulta sem controle de orçamento.

### O que a amostra responde

| Pergunta | Uso |
| --- | --- |
| O XGBoost concorda com as hard rules? | Mede sobreposição e ganho marginal por camada |
| Qual a taxa de fraude entre negados por hard rule? | Detecta regra obsoleta ou excessivamente ampla |
| O HBOS é discriminativo na população que ele não vê? | Avalia a generalização fora do recorte da regra 83 |
| O score consolidado está calibrado? | Compara score previsto contra fraude observada por banda |
| Há divergência por coorte? | Alimenta a avaliação de viés |
| O challenger supera o champion na população completa? | Sustenta a decisão de promoção |

### Monitoramento derivado do trace

- Distribuição de camada terminal (quem decide, na prática — resolve as divergências D-1 a D-3 do
  [AS-IS](../arquitetura/as-is.md)).
- Distribuição de scores por camada e por banda de risco.
- Taxa de fallback por camada e por motivo.
- Duração por camada, contra o orçamento de latência declarado no [TO-BE](../arquitetura/to-be.md).
- Cobertura do trace: proporção de transações com trace completo (meta: 100%, descarte medido).
- Fraude confirmada por banda de score, por versão de modelo.

## Critérios de aceite

| # | Critério | Como comprovar |
| --- | --- | --- |
| CA-O.1 | 100% das transações possuem decision trace com os campos obrigatórios | Consulta de cobertura por período; validação de schema no consumidor rejeita registro incompleto |
| CA-O.2 | Camada terminal registrada em toda decisão | Distribuição de camada terminal sem categoria "desconhecida" |
| CA-O.3 | Camadas não executadas explicitamente listadas | Registro distingue "não executada" de "executada sem sinal"; score ausente é `null`, não `0` |
| CA-O.4 | Amostra em shadow entre 1% e 5%, configurável sem redeploy | Alteração da taxa aplicada e observada no volume de registros de shadow |
| CA-O.5 | Shadow não afeta decisão nem latência | Comparação A/B de p95 entre transações amostradas e não amostradas sem diferença significativa; zero notificações originadas de shadow |
| CA-O.6 | Divergência entre camadas medida e publicada | Relatório periódico de concordância/divergência entre hard rules, HBOS, XGBoost e challenger |
| CA-O.7 | Perda de trace medida | Métrica de descarte de trace publicada com alerta acima do limite definido |
