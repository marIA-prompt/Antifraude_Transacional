# Acompanhamento de modelagem (MAPA) — escassez de rótulos

Fonte: *MAPA — Método de Acompanhamento de Projetos em Dados* (Osterne / Morais), tema
"Desenvolvimento e Validação de Estratégias de Modelagem para um Sistema Antifraude com
Escassez de Rótulos".

Este documento **não altera** a arquitetura do microserviço. O MAPA declara a arquitetura
como restrição de contorno, fora do escopo direto do acompanhamento. A contribuição é o
protocolo de diagnóstico e avaliação de modelagem.

> AutoML, agentes e novos modelos **não são fechados** aqui. Nenhuma linha de modelagem se
> encerra antes da Etapa 1.

## AS-IS (premissas do MAPA, a confirmar)

O MAPA parte da documentação então disponível:

- motor de score online, p95 < 100 ms;
- Regra 83 como gate: transações que não a acionam aprovadas sem escore;
- demais passam por HBOS individual por CPF e, em reprovação/dúvida, por XGBoost;
- ausência relatada de fraudes confirmadas nos últimos seis meses.

| Camada | Conteúdo |
|---|---|
| **AS-IS deste repositório** | O briefing versão final **não** descreve a Regra 83 como gate do FastAPI. Essa premissa do MAPA é [D-3](../arquitetura/divergencias-documentais.md) — item aberto |
| **Lacuna/Risco** | Fechar estratégia de modelagem sobre um gate não confirmado enviesa treino e métricas |
| **TO-BE** | Etapa 1 substitui premissa por evidência (trace, código, volume) |
| **Critério de aceite da Etapa 1** | Ata/registro com: (a) ordem real Autenticador / NEG83 / `score-transaction`; (b) volume e taxa de fraude das fatias com e sem a regra, se ela existir; (c) threshold efetivo do `deny` terminal do HBOS |

A ausência de fraude confirmada em seis meses **não** autoriza concluir que o retreino
supervisionado está inviabilizado: pode haver fraudes históricas, rótulos atrasados,
contestações/chargebacks não incorporados, falha de rotulagem ou mudança de política.

## Etapas (ordem obrigatória)

### Etapa 1 — Diagnóstico do fluxo AS-IS

Confirmar com o time, não com a documentação:

1. fluxo realmente em produção, inclusive divergências D-1 a D-4;
2. existência, formato e volume de rótulos históricos (casos antigos, contestações,
   chargebacks);
3. por que não há fraude confirmada recente: ausência real, falha de detecção, política ou
   atraso de maturação;
4. janela real do HBOS, regra de passagem HBOS → XGBoost, escopo da base de treino.

**Critério de aceite:** documento de diagnóstico versionado; zero escolha de modelo nova
citando esta etapa como pendente.

### Etapa 2 — Auditoria de fontes de rótulo e janela de maturação

Avaliar isoladamente, antes de combinar:

| Fonte | Uso permitido | Risco |
|---|---|---|
| `fraude_confirmada` | rótulo positivo maduro | janela de maturação a medir (dias) |
| Resposta de challenge / WhatsApp | sinal de supervisão, não desfecho definitivo | confrontar com contestação/chargeback posterior |
| Hard rules como pseudo-rótulo | só como hipótese, contra baseline simples | circularidade: o modelo reproduz a regra (ex.: NEG83) sem ganho |
| Bureau / blocklist / geo / device | se viável técnica, jurídica e operacionalmente | não substitui desfecho interno |

**Critério de aceite:** tabela com volume, atraso mediano de maturação, taxa de
reclassificação posterior e decisão de uso (entra / não entra / só shadow) por fonte.

### Etapa 3 — Base analítica e viés de seleção

Se a Etapa 1 confirmar que o treino é essencialmente `{x : gate = 1}`, há viés de seleção
estrutural. Quantificar comparando a distribuição das variáveis em `gate = 1` vs `gate = 0`.
Efeito sobre detecção só é mensurável se existirem desfechos fora do gate (telemetria,
shadow).

`sem_desfecho` **não** é classe negativa.

**Critério de aceite:** PSI (ou equivalente) por feature entre as duas fatias; se o gate não
existir (D-3), o relatório declara "gate não observado" e o viés a medir passa a ser o do
short-circuit HBOS `deny` (camada não executada).

### Etapa 4 — Baseline dos componentes atuais

Antes de modelo novo: desempenho da (eventual) Regra 83, do HBOS e do XGBoost, isolados e em
conjunto. Componentes rodam em cascata sobre subconjuntos diferentes — comparação isolada
exige amostra comum (score retrospectivo ou shadow). Sem isso, o baseline é a política
completa, com limitações explícitas.

**Critério de aceite:** PR-AUC / precisão-revocação e métricas de custo da política vigente,
com denominador declarado (quem entrou em cada camada). Acurácia não é métrica principal.
AUC-ROC interpretada com cautela em evento raro.

### Etapa 5 — Comparação de estratégias (só depois de 1–4)

Candidatas condicionadas ao que existir de dado:

1. HBOS como sinal contínuo de desvio, não classificador binário;
2. pseudo-rótulos (Etapa 2) com risco de circularidade quantificado;
3. sinais externos autorizados, se empiricamente relevantes;
4. combinação HBOS + XGBoost como hipótese a testar — escalas podem diferir; a média
   ponderada AS-IS não é forma funcional fechada.

**Critério de aceite:** cada candidata contra o baseline da Etapa 4, split temporal, com
intervalo de confiança ou bootstrap; promoção só via [MLOps](dados-rotulos-e-promocao.md).

### Etapa 6 — Protocolo de validação, métricas e thresholds

Priorizar, quando houver desfechos suficientes:

- curva precisão-revocação (PR-AUC) e custo assimétrico FP/FN;
- validação estritamente temporal, sem leakage, respeitando a janela de maturação da Etapa 1;
- métricas operacionais: precisão nos desafiados, recall sob capacidade fixa de análise,
  taxa de challenge, taxa de aprovação, fraude evitada, custo esperado de FP/FN;
- thresholds em função de custo e capacidade da fila, não da maximização de uma métrica;
- estabilidade de escores no tempo quando não houver rótulo para calibração formal.

Calibração isotônica/Platt **não** se apresenta como concluída sem quantidade e
representatividade mínimas de desfechos.

Alinhamento com AutoML offline, se usado: `primary_metric: average_precision_score_weighted`.

### Etapa 7 — Cold start, combinação de escores e calibração

Somente após 1–6, e só se o diagnóstico confirmar necessidade. A confiabilidade do HBOS
tende a depender da maturidade do histórico — **hipótese a verificar**, não peso a priori.
A política operacional mínima já está em [ADR-0003](../adr/0003-politica-de-cold-start.md)
(`X`, `Y`, `cold_start`); este acompanhamento pode refinar a forma funcional dos pesos.

### Etapa 8 — Próximos passos de reunião

Ordem: (i) Etapa 1; (ii) Etapa 2; (iii) Etapa 3 se houver dado; (iv) Etapa 4. Só então
estratégias, protocolo, cold start e calibração.

## Relação com o roadmap de engenharia

| MAPA | Engenharia |
|---|---|
| Etapa 1–2 | Fase 0 (telemetria/shadow) e perguntas abertas do AS-IS |
| Etapa 3–4 | Relatórios da amostra shadow 1%–5% |
| Etapa 5–6 | Fase 6 (calibração e challengers), AutoML só offline ≥ 4 semanas |
| Etapa 7 | Refino da [ADR-0003](../adr/0003-politica-de-cold-start.md), depois da Fase 1 |
