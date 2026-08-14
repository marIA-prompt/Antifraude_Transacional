# Contexto AS-IS do motor de score antifraude

Documento de referência do estado atual. Tudo aqui descreve o que existe hoje ou o que é
sabidamente ambíguo. Propostas de evolução ficam nos ADRs em [`docs/adr/`](../adr/).

> Convenção usada em todos os documentos deste repositório:
> **AS-IS** (o que existe) · **Lacuna/Risco** (limitação ou risco operacional) ·
> **TO-BE** (evolução proposta) · **Critério de aceite** (como comprovar objetivamente).

## AS-IS: fluxo de decisão vigente

O sistema é um microserviço de score antifraude para transações de cartão de crédito
(inclui produto private label), com decisão online em baixa latência. A meta de performance
é **p95 abaixo de 100 ms no fast path de approve/deny**.

O fluxo vigente usa a Regra 83 como *gate de entrada* dos modelos:

```text
Transação
→ caiu na Regra 83?
   → NÃO  : aprovado (terminal, sem passar por nenhum modelo)
   → SIM  : motor HBOS individual por CPF
       → HBOS aprovado          : terminal (XGBoost não é executado)
       → HBOS reprovado/challenge: XGBoost global
           → decisão final: aprovado / reprovado / challenge
```

Três propriedades desse desenho precisam ficar explícitas, porque condicionam todo o resto:

1. **A cobertura de ML está condicionada a uma única regra.** HBOS e XGBoost só avaliam o
   subconjunto de transações que aciona a Regra 83; o restante do tráfego é aprovado sem escore.
2. **O approve do HBOS é terminal.** Nunca é auditado pelo modelo supervisionado.
3. **O XGBoost pode reverter o "reprovado" do HBOS** e é ele quem emite a decisão final,
   inclusive a banda `challenge`.

### Divergência documental registrada

A especificação textual do microserviço descreve uma cascata diferente
(`validação → features → HBOS → regras/hard rules → XGBoost → decisão`), aplicada a todo o
tráfego. **Essa descrição é tratada aqui como desenho anterior ou aspiracional, não como
produção.** A referência de AS-IS é o fluxo com gate da Regra 83 descrito acima.

## AS-IS: componentes de decisão

### HBOS individual por CPF

- Modelo não supervisionado de detecção de anomalias, treinado offline por CPF.
- Compara a nova transação com o comportamento histórico do próprio cliente.
- Servido a partir de *bundles* com modelo, scaler, perfis estatísticos e metadados,
  carregados em cache de memória.
- Janela de histórico de aproximadamente até 730 dias.
- Score alto significa comportamento atípico, **não prova de fraude**. Deve ser tratado como
  sinal comportamental, não como classificador determinístico.

### XGBoost global

- Modelo supervisionado treinado com rótulos históricos de fraude/não fraude.
- Aprende padrões globais e interações entre features; complementa o HBOS, sobretudo para
  CPF novo ou com histórico insuficiente.
- Depende da qualidade, maturação e representatividade dos rótulos.
- Exige validação com divisão temporal e controles contra leakage.

### Regras de negócio e hard rules

- Regras determinísticas complementam os modelos: horário, valor, parcelas, estabelecimento
  novo, geolocalização, device intelligence, blocklists e viagem impossível.
- Hard rules críticas podem prevalecer sobre scores probabilísticos.
- Toda regra deve gerar evidência e reason code auditável.

### Step-up via WhatsApp (private label)

Existe um fluxo operacional real de confirmação de compra via WhatsApp, acionado pela
Regra 83 no produto private label: confirmação do cliente resulta em compra aprovada, e a
ausência de confirmação resulta em compra negada.

## AS-IS: contrato da API

A resposta HTTP atual expõe apenas a decisão:

```json
{ "decision_final": "approve | challenge | deny" }
```

A especificação original previa cinco saídas estruturadas (`score`, `decision`, `signals`,
`features`, `feature_weights`). Score, sinais, features e pesos hoje permanecem apenas em
logs ou eventos internos. O tratamento proposto está em
[`docs/contratos/api-versionada.md`](../contratos/api-versionada.md).

## Lacunas e riscos consolidados

| # | Lacuna / Risco | Impacto | Tratamento proposto |
|---|---|---|---|
| L1 | Cobertura de ML condicionada ao gate da Regra 83 | Fraude que não aciona a regra é aprovada sem escore; viés de seleção estrutural no retreinamento | [ADR-0001](../adr/0001-topologia-de-decisao.md) |
| L2 | Approve terminal do HBOS decide sozinho | Contradiz o papel de sinal comportamental; fraude de baixo desvio passa sem o modelo global | [ADR-0002](../adr/0002-papeis-dos-modelos.md) |
| L3 | `challenge` sem fluxo operacional completo | Caso classificado como questionável pode não acionar fila, step-up, análise humana ou notificação | [Trilha de challenge](../workflows/trilha-de-challenge.md) |
| L4 | Step-up do WhatsApp acoplado à Regra 83 e restrito ao private label | Não reutilizável; não-resposta vira deny automático, sem escalonamento humano | [Trilha de challenge](../workflows/trilha-de-challenge.md) |
| L5 | Cache de modelos exige restart ou limpeza manual após retreino | Instâncias servindo versões antigas sem detecção | [ADR-0004](../adr/0004-publicacao-de-modelos-e-cache.md) |
| L6 | Cold start de CPF novo indefinido neste fluxo | CPF sem bundle HBOS não tem caminho documentado; aprovação padrão eleva exposição | [ADR-0003](../adr/0003-politica-de-cold-start.md) |
| L7 | Short-circuit oculta a performance das camadas posteriores | Impossível medir camadas não executadas; viés de seleção para retreino | [Telemetria de decisão](../observabilidade/telemetria-de-decisao.md) |
| L8 | API v1 não expõe explicabilidade | Consumidores autorizados sem acesso a score, sinais e pesos; orquestração tende a acoplar-se ao HTTP | [Contrato versionado](../contratos/api-versionada.md) |
| L9 | Rótulos sujeitos a maturação tardia | `sem_desfecho` tratado como legítima corrompe o treino | [MLOps](../mlops/dados-rotulos-e-promocao.md) |

## Perguntas abertas

Itens que dependem de confirmação do time e que, enquanto não resolvidos, ficam registrados
como premissa explícita nos ADRs:

1. Qual o volume relativo do tráfego que **não** aciona a Regra 83, e qual a taxa de fraude
   confirmada nessa fatia? Sem esse número não é possível dimensionar o risco de L1.
2. Qual o threshold efetivo do approve terminal do HBOS e onde ele está configurado?
3. O step-up via WhatsApp existe fora do private label?
4. Qual a janela real de maturação de rótulo (dias entre transação e confirmação de fraude)?
5. Existe model registry hoje, ainda que informal (bucket versionado, convenção de nomes)?
