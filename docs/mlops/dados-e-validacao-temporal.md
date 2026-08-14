# Qualidade de dados, validação temporal, rótulos e drift

Endereça `LR-07` e `LR-08`. Estes controles são condição de entrada para qualquer treinamento,
inclusive AutoML offline.

## 1. Qualidade de dados

Controlar continuamente, com bloqueio de pipeline quando o limite é violado:

| Verificação | Por que importa em antifraude |
| --- | --- |
| Nulos | Feature nula tratada como zero vira "comportamento normal" e apaga sinal |
| Duplicidades | Mesma transação repetida distorce prevalência de fraude e infla histórico |
| Replays | Reenvio pode ser tanto falha de integração quanto ataque; confundir os dois corrompe rótulo |
| Estornos | Estorno legítimo confundido com fraude gera rótulo errado |
| Timestamps inválidos ou futuros | Quebram ordenação temporal e habilitam leakage |
| Valores fora de faixa | Sinal de erro de integração ou de manipulação de payload |
| Dados geográficos inválidos | Alimentam falsos positivos de viagem impossível |
| Mudanças de schema | Feature deslocada continua sendo número válido: falha silenciosa |
| Proporção de CPF novo | Salto pode ser campanha comercial ou ataque de aquisição |
| Cobertura de campos por canal | Canal que não envia device deixa a camada cega |
| Features com risco de leakage temporal | Ver seção 2 |

Cada verificação declara limite, severidade e ação (alerta, bloqueio do treino, bloqueio da
publicação). Verificação sem ação definida é relatório, não controle.

## 2. Validação temporal e leakage

Treino, validação e teste respeitam a linha do tempo. Uma transação histórica **não pode** usar
dados, status ou features disponíveis apenas após sua ocorrência.

```text
Treino: janeiro a setembro
Validação: outubro
Teste temporal: novembro
Produção/monitoramento: dezembro em diante
```

Fontes de leakage específicas deste sistema, a verificar explicitamente:

- **Status de contestação ou chargeback** usado como feature: só existe depois da transação.
- **Agregados de janela** calculados sobre a janela completa do dataset em vez de "até o instante da
  transação" (por exemplo, média de valor do CPF incluindo transações posteriores).
- **Bundle HBOS treinado com dados posteriores** à transação avaliada: o perfil individual precisa ser
  o vigente no momento da decisão, não o mais recente disponível.
- **Blocklist atual** aplicada retroativamente: o CPF pode ter entrado na lista depois do evento.
- **Desfecho de `challenge`** usado como feature de entrada, e não como rótulo.

Controle prático: cada feature declara sua **disponibilidade em tempo de decisão**. Feature que não
consegue declarar isso não entra em treino.

## 3. Maturação de rótulos

Fraudes podem ser confirmadas dias ou semanas após a transação. Categorias:

```text
fraude_confirmada
fraude_suspeita
em_disputa
legitima_confirmada
sem_desfecho
```

**`sem_desfecho` não é transação legítima.** Tratar assim significa ensinar o modelo a aprovar fraude
que ainda não foi contestada, e inflar artificialmente a precisão medida — o erro fica invisível
porque o próprio rótulo o esconde.

Consequências práticas:

- **Janela de maturação declarada** por tipo de fraude: dataset de treino usa apenas o período cuja
  maturação já se completou.
- **Períodos recentes são excluídos** do treino supervisionado, ainda que estejam disponíveis.
- **`sem_desfecho` é excluído ou recebe tratamento explícito** (peso, modelagem de censura), nunca
  reclassificação silenciosa para legítimo.
- **Rótulo é versionado**: o mesmo `transaction_id` muda de categoria com o tempo, e a métrica de um
  modelo precisa declarar em qual instantâneo de rótulo foi calculada.
- **Reprocessamento de métrica** após maturação, para corrigir avaliações otimistas.

## 4. Monitoramento de drift

| Grupo | O que acompanhar |
| --- | --- |
| Distribucional | PSI e KS por feature; distribuição de scores; taxa de nulos |
| Transacional | Volume, ticket médio, horários, parcelas |
| Segmentação | Canais, estabelecimentos, regiões, dispositivos, taxa de CPF novo |
| Desempenho | Fraude confirmada por banda de score |
| Consistência entre modelos | Divergência entre HBOS, XGBoost e challenger |

Notas de interpretação que evitam conclusão errada:

- **Drift não é degradação por si.** Campanha comercial, sazonalidade e novo canal deslocam
  distribuição sem que o modelo tenha piorado. A conclusão exige olhar performance junto.
- **Performance recente é enviesada por maturação.** "Fraude confirmada por banda" nos últimos dias
  parece melhor do que é, porque a fraude ainda não amadureceu. Comparar sempre janelas de maturação
  equivalentes.
- **Drift de score pode ser efeito de publicação de modelo**, não do mundo: correlacionar com
  `model_version` antes de investigar o ambiente.
- **Alerta precisa de ação associada**: investigar, retreinar, ajustar threshold ou reverter. Alerta
  sem dono e sem ação vira ruído ignorado.

## Critérios de aceite

| # | Critério | Como comprovar |
| --- | --- | --- |
| CA-D.1 | Verificações de qualidade executam a cada carga, com ação declarada | Relatório de execução com resultado por verificação e evidência de bloqueio em caso de violação |
| CA-D.2 | Nenhum treino usa split não temporal | Pipeline falha ao receber split aleatório; registro do intervalo de cada partição no metadado do modelo |
| CA-D.3 | Toda feature declara disponibilidade em tempo de decisão | Catálogo de features completo; feature sem declaração bloqueia o treino |
| CA-D.4 | `sem_desfecho` nunca é tratado como legítimo | Teste no pipeline de rotulagem; contagem por categoria registrada no metadado do dataset |
| CA-D.5 | Janela de maturação respeitada | Data máxima do dataset de treino ≤ data de corte − janela de maturação, verificada automaticamente |
| CA-D.6 | Rótulos versionados | Métrica de modelo referencia o instantâneo de rótulo usado |
| CA-D.7 | Drift monitorado com alerta e dono | Painel ativo com limites definidos e runbook de resposta por tipo de alerta |
| CA-D.8 | Teste anti-leakage | Verificação automatizada compara métrica temporal contra métrica aleatória; diferença anômala em favor da aleatória bloqueia a promoção |
