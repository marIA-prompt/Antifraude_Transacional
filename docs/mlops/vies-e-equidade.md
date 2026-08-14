# Viés e equidade

Endereça `LR-09`, `LR-10` e o componente de equidade de `LR-04` e `LR-05`.

O viés precisa ser avaliado no **processo completo**, não apenas no modelo: dados, regras, cascata,
short-circuit, rotulagem e retreinamento. Um modelo perfeitamente balanceado dentro de uma cascata
que só o consulta para uma subpopulação selecionada por regra determinística continua produzindo
resultado desigual.

## Riscos principais

| Risco | Mecanismo concreto neste sistema |
| --- | --- |
| CPF novo e clientes com pouco histórico | Sem base comportamental, o HBOS produz anomalia espúria; qualquer transação parece atípica |
| Clientes legítimos com comportamento naturalmente variável | Autônomo, viajante, comprador sazonal: atipicidade é o normal dele, e o HBOS pune isso |
| Geolocalização imprecisa ou desigual entre regiões | Precisão de IP e cobertura variam por região; erro de localização vira "viagem impossível" |
| Tipo de comércio como proxy indevido de risco | MCC correlaciona com perfil socioeconômico; risco do estabelecimento é atribuído ao cliente |
| Regras históricas que geram viés de seleção | A regra 83 define quem o modelo vê; o modelo herda o recorte da regra |
| Rótulos que refletem maior investigação em certos segmentos | Onde se investiga mais, confirma-se mais fraude; o modelo aprende o padrão de investigação, não o de fraude |
| Amplificação de sinais correlacionados em múltiplas camadas | Mesma evidência (device novo) pesa em regra, no HBOS e no XGBoost: risco somado três vezes pela mesma causa |

O caso da rotulagem merece destaque porque é contraintuitivo: se historicamente se investiga mais um
canal ou uma região, a base tem mais fraude confirmada ali, e o modelo aprende a associar aquele
segmento a fraude — reforçando a investigação, que reforça o rótulo. O ciclo se fecha e parece
performance.

## Controles

### 1. Métricas por coorte

Coortes de avaliação obrigatórias — atributos operacionais, não atributos protegidos:

- tempo de relacionamento (inclui o nível de confiança do histórico do
  [cold start](../evolucoes/03-cold-start.md));
- volume histórico;
- canal;
- região operacional;
- tipo de comércio;
- qualidade dos dados disponíveis (cobertura de campos por canal).

Comparar por coorte: **FPR, FNR, recall, precisão, taxa de `challenge` e taxa de `deny`**.

Regras de leitura: declarar volume mínimo antes de concluir diferença; comparar em janelas de
maturação equivalentes; e diferença de taxa de fraude real entre coortes é risco, não viés — o sinal
de viés é FPR/FNR desigual **em risco equivalente**.

### 2. Controle de proxies

Nenhum atributo protegido é usado como feature. Isso não é suficiente: CEP, MCC, tipo de dispositivo,
canal e horário podem funcionar como proxy. Controle: revisão explícita de features com potencial de
proxy, avaliação da contribuição delas (feature importance e SHAP) e teste de impacto ao removê-las.

### 3. Peso do HBOS por confiança do histórico

Reduzir o peso do HBOS quando o histórico é insuficiente é simultaneamente controle de qualidade e
controle de equidade: elimina a penalização estrutural de quem acabou de chegar. Implementado na
[Evolução 3](../evolucoes/03-cold-start.md).

### 4. Limite ao impacto cumulativo de sinais correlacionados

Sinais que compartilham causa raiz não devem somar risco de forma independente. Controles: agrupar
sinais por família (device, geografia, velocidade, valor), limitar a contribuição máxima por família e
medir a correlação entre sinais acionados antes de tratá-los como evidência adicional.

### 5. Revisão humana em baixa confiança e alto impacto

`escalate` existe para isso. Caso de baixa confiança do modelo ou de alto impacto para o cliente
precisa de decisão humana — e a decisão humana é registrada com evidência, tanto para auditoria como
para medir a qualidade do automatismo.

### 6. Medição de reversões

Reversão após step-up e após análise humana é o melhor estimador disponível de **falso positivo**:
casos que o motor marcou e a verificação absolveu. Medir por coorte expõe onde o motor erra mais
contra quem. Reversão concentrada em uma coorte é evidência de viés, não anedota.

### 7. Viés na trilha de `challenge`

O viés não termina na decisão online. Avaliar também: distribuição de `escalate` por coorte, tempo
até desfecho por coorte (esperar mais é atrito real), taxa de step-up inalcançável por região ou
canal e disponibilidade de canal de step-up por segmento.

## Critérios de aceite

| # | Critério | Como comprovar |
| --- | --- | --- |
| CA-V.1 | Métricas por coorte publicadas periodicamente | Relatório com FPR, FNR, recall, precisão, taxa de `challenge` e `deny` por coorte, com volume e intervalo de confiança |
| CA-V.2 | Nenhuma promoção sem avaliação de viés | Ficha de promoção contém a seção por coorte; ausência bloqueia a promoção |
| CA-V.3 | Regressão por coorte é gatilho de rollback | Alerta configurado por coorte com limite declarado |
| CA-V.4 | Proxies revisados | Lista de features com potencial de proxy, com contribuição medida e decisão registrada |
| CA-V.5 | Peso do HBOS reduzido sob histórico insuficiente | `feature_weights` comprova em amostra de transações de CPF novo |
| CA-V.6 | Contribuição por família de sinal limitada | Teste de cenário com múltiplos sinais correlacionados demonstra o teto aplicado |
| CA-V.7 | Reversões medidas por coorte | Painel de reversão pós-step-up e pós-análise humana segmentado |
| CA-V.8 | Equidade avaliada também na trilha de challenge | Relatório com tempo até desfecho e taxa de inalcançabilidade por coorte |
