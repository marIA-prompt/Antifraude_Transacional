# Dados, rótulos, viés e promoção de modelos

## O problema que precede qualquer escolha de modelo

### Lacuna/Risco: viés de seleção estrutural

No fluxo vigente, os modelos só observam o tráfego que aciona a Regra 83, e os rótulos futuros
vêm desse mesmo recorte. Treinar num universo filtrado pela própria política e medir performance
nele é viés de seleção clássico: PR-AUC e recall calculados assim não descrevem a população real,
e o modelo tende a se especializar progressivamente no que a regra já capturava.

Enquanto isso não for tratado, **nenhuma métrica de promoção de modelo é confiável**, porque o
denominador está truncado.

### TO-BE: duas fontes de dados não enviesados

**1. Shadow scoring de 1% a 5% de todo o tráfego, inclusive fora do gate.** Custo de risco zero,
porque não interfere na decisão online. Já é suficiente para revelar quanta fraude o gate deixa
passar, por banda de escore. É pré-requisito, não melhoria opcional.

**2. Amostra de exploração controlada** — opcional, com teto de exposição financeira definido e
aprovado. Aprovação com monitoramento reforçado de uma fração pequena de casos na faixa de risco
baixo-intermediário, para gerar rótulos contrafactuais onde a política atual sempre nega. Sem
isso, a região do espaço de features que a política nunca aprova permanece permanentemente sem
observação. O teto de perda esperada deve ser explícito e monitorado.

## Qualidade de dados

Controles contínuos, com alerta:

- nulos e duplicidades;
- replays e estornos;
- timestamps inválidos ou futuros;
- valores fora de faixa;
- dados geográficos inválidos;
- mudanças de schema;
- proporção de CPF novo;
- cobertura de campos por canal;
- features com risco de leakage temporal.

Falha de qualidade acima do limite configurado deve **bloquear o pipeline de treino**, não
apenas alertar.

## Validação temporal

Treino, validação e teste respeitam a linha do tempo. Uma transação histórica não pode usar
dados, status ou features disponíveis apenas após sua ocorrência.

```text
Treino:                   janeiro a setembro
Validação:                outubro
Teste temporal:           novembro
Produção/monitoramento:   dezembro em diante
```

Split aleatório é proibido para avaliação de performance. Toda feature precisa ter o instante de
disponibilidade documentado, e a auditoria de leakage é parte da validação do artefato — não uma
revisão informal.

## Maturação de rótulos

Fraudes são confirmadas dias ou semanas após a transação. Categorias usadas:

```text
fraude_confirmada
fraude_suspeita
em_disputa
legitima_confirmada
sem_desfecho
```

Regras que valem sempre:

- **`sem_desfecho` nunca é tratado como legítima.** É a fonte mais comum de otimismo artificial
  em métricas de fraude.
- O corte de treino respeita a janela de maturação: transações recentes demais para terem rótulo
  estável não entram como negativas.
- Rótulos derivados do step-up entram distintos: negação explícita do titular é sinal forte;
  não-resposta é ausência de informação, não fraude (ver
  [trilha de challenge](../workflows/trilha-de-challenge.md)).

## Monitoramento de drift

- PSI e KS por feature;
- distribuição de escores por modelo;
- taxa de nulos;
- volume transacional e ticket médio;
- horários, parcelas, canais, estabelecimentos, regiões, dispositivos;
- taxa de CPF novo;
- fraude confirmada por banda de escore;
- divergência entre HBOS, modelo global e challenger.

## Viés e equidade

O viés é avaliado no **processo completo** — dados, regras, cascata, short-circuit, rotulagem e
retreinamento — não apenas no modelo isolado.

### Riscos principais

- CPF novo e clientes com pouco histórico;
- clientes legítimos com comportamento naturalmente variável;
- geolocalização imprecisa ou desigual entre regiões;
- tipo de comércio como proxy indevido de risco;
- regras históricas que geram viés de seleção;
- rótulos que refletem maior investigação em certos segmentos;
- amplificação de sinais correlacionados em múltiplas camadas.

O último merece atenção especial na topologia paralela do
[ADR-0001](../adr/0001-topologia-de-decisao.md): quando várias camadas leem o mesmo sinal
subjacente (por exemplo, geolocalização entrando em regra, feature do modelo e feature de grafo),
o efeito é contado múltiplas vezes. A camada de política precisa limitar a contribuição cumulativa
de sinais correlacionados.

### Controles

- métricas por coorte: tempo de relacionamento, volume histórico, canal, região operacional,
  tipo de comércio e qualidade dos dados;
- comparação de FPR, FNR, recall, precisão, taxa de challenge e taxa de deny por coorte;
- controle de proxies de atributos protegidos;
- peso reduzido do HBOS quando o histórico é insuficiente
  ([ADR-0003](../adr/0003-politica-de-cold-start.md));
- limite do impacto cumulativo de sinais correlacionados;
- revisão humana em casos de baixa confiança ou alto impacto;
- medição de reversões após step-up e análise humana.

## AutoML: uso permitido

**Permitido, offline:** testar modelos de classificação e regressão, avaliar estratégias de
featurização, comparar candidatos contra HBOS e o modelo global, gerar feature importance e SHAP,
apoiar a estratégia champion/challenger.

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

**Não permitido:**

```text
Transação online → chamada remota ao AutoML → decisão de autorização
```

O serviço de autorização consome apenas artefatos já aprovados, versionados, serializados e
disponíveis em cache ou armazenamento de baixa latência.

## Métricas mínimas para promoção

Nenhum modelo é promovido com base em acurácia ou em qualquer métrica isolada. O conjunto
completo é obrigatório:

| Categoria | Métricas |
|---|---|
| Discriminação | PR-AUC, ROC-AUC, recall de fraude, precisão |
| Erro | False Positive Rate, False Negative Rate |
| Operação | taxa de `challenge`, taxa de aprovação legítima, custo operacional |
| Confiabilidade | calibração, estabilidade temporal |
| Negócio | custo evitado, fraude residual |
| Sistema | latência |
| Equidade | métricas por coorte |
| Governança | explicabilidade |

## Rollout e promoção

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

Estados no model registry: `candidate`, `challenger`, `champion`, `deprecated`, `rolled_back`
(ver [ADR-0004](../adr/0004-publicacao-de-modelos-e-cache.md)).

A promoção considera performance, calibração, explicabilidade, latência, estabilidade temporal,
viés, custo operacional, falsos positivos, fraude evitada e impacto na experiência do cliente.

## Critérios de aceite

- Shadow scoring ativo cobrindo tráfego dentro e fora do gate, com amostragem configurável entre
  1% e 5%.
- Relatório de fraude confirmada por banda de escore na população fora do gate.
- Pipeline de treino bloqueado automaticamente quando os limites de qualidade de dados são
  violados.
- Nenhum conjunto de avaliação construído por split aleatório; split temporal comprovado por
  metadados do experimento.
- Nenhuma transação `sem_desfecho` usada como negativa, verificado por teste do pipeline.
- Janela de maturação de rótulo documentada e aplicada ao corte de treino.
- Negação explícita e não-resposta ao step-up armazenadas como categorias distintas.
- Métricas por coorte publicadas em toda avaliação de promoção, com comparação de FPR, FNR,
  recall, precisão, taxa de challenge e taxa de deny.
- Promoção bloqueada quando qualquer métrica do conjunto mínimo estiver ausente.
- Nenhuma chamada remota a AutoML no caminho de autorização, verificado por teste de contrato.
