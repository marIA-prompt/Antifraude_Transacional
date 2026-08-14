# ADR-0002 — Papéis dos modelos: HBOS, GBDT global, calibração e consolidação

- **Status:** proposto
- **Depende de:** [ADR-0001](0001-topologia-de-decisao.md)
- **Lacunas endereçadas:** L2 (approve terminal do HBOS), L6 (cold start), L9 (rótulos)

## Contexto

Os modelos existentes são adequados ao problema. O que precisa ser corrigido é o **papel** de
cada um na decisão e a ausência de uma etapa explícita de calibração. Este ADR fixa o
inventário de modelos, o que cada um pode e não pode decidir, e o que fica fora do hot path.

## Decisão: inventário e papéis

### Regras determinísticas e hard rules — soberanas onde a política exige certeza

Continuam sendo a camada de maior autoridade nos casos em que o negócio exige decisão certa
(blocklist confirmada, device banido, viagem impossível). O que muda é que regras deixam de
determinar *quem é elegível a ser analisado*: a Regra 83 passa a ser sinal, conforme ADR-0001.

Toda regra produz evidência e reason code. Nenhum modelo — e nenhum agente de IA — sobrepõe
uma hard rule crítica.

### HBOS individual por CPF — sinal comportamental, nunca decisor

Mantido. É a escolha correta para o papel:

- treino offline barato por cliente, sobre janela de até ~730 dias;
- inferência na casa de microssegundos a partir de bundle em cache de memória;
- **explicabilidade nativa**: a contribuição por feature sai do próprio histograma, o que
  alimenta reason codes sem custo de SHAP em tempo real.

Restrições que passam a valer:

- o HBOS **não emite decisão terminal**; contribui com escore e contribuições por feature para
  a camada de política;
- seu peso cai a zero ou é reduzido quando o histórico é insuficiente
  ([ADR-0003](0003-politica-de-cold-start.md));
- escore alto é comportamento atípico, não prova de fraude — a redação dos reason codes deve
  refletir isso, inclusive nos textos expostos a analista humano.

Sinal auxiliar recomendado: um z-score robusto por mediana/MAD calculado sobre os mesmos
perfis. É barato, resistente a caudas longas e serve de sanidade contra bundle degradado ou
scaler desatualizado.

### GBDT global — champion supervisionado

Mantido como o modelo de risco global, dependente de rótulos maduros e validação temporal
estrita (ver [MLOps](../mlops/dados-rotulos-e-promocao.md)).

**LightGBM entra como challenger do XGBoost**, não como substituição decidida: a hipótese é
latência e memória mais previsíveis com features categóricas de alta cardinalidade (merchant,
MCC, faixa de device). A troca só se justifica se validada pelo mesmo pipeline de promoção.

### Calibração explícita — artefato de primeira classe

GBDT devolve escore, não probabilidade. Sem calibração, os thresholds de `challenge` e `deny`
derivam silenciosamente a cada retreino: a taxa de challenge muda sem que ninguém tenha
alterado política, e a fila de triagem absorve o efeito.

Decisão: calibração isotônica ou Platt ajustada em janela temporal recente, **versionada e
publicada junto ao modelo**, com a versão registrada em toda inferência. Deriva de calibração
é monitorada com alerta próprio.

### Consolidação por política determinística, não por meta-modelo

Rejeitada a opção de empilhar um modelo de stacking sobre HBOS + GBDT + regras. O ganho
marginal não paga a perda de auditabilidade (qual camada elevou o risco) nem o custo de
monitorar um segundo modelo.

Se um combinador aprendido for necessário, a forma aceita é **regressão logística sobre um
conjunto pequeno de sinais**: coeficientes legíveis, `feature_weights` diretos para a API v2 e
explicação defensável diante de contestação de cliente ou de revisão de decisão automatizada
(art. 20 da LGPD).

### Modelo dedicado de cold start

Um segundo GBDT treinado **sem nenhuma feature derivada do histórico do CPF**, usando apenas
atributos da transação, device, merchant, geolocalização e agregados de curto prazo. Isso trata
o cold start melhor do que zerar features em um modelo que aprendeu a confiar nelas: o modelo
global com features de histórico ausentes tende a produzir escores mal calibrados exatamente na
coorte mais exposta. Detalhes em [ADR-0003](0003-politica-de-cold-start.md).

### Sinais de grafo — pré-computados, consultados no hot path

Compartilhamento de device entre CPFs, CPFs por merchant, componentes conexos suspeitos.
Historicamente é o maior ganho de recall em fraude de cartão. Compatível com o orçamento de
latência **desde que materializado offline ou em near-real-time** e apenas consultado durante a
autorização. Cálculo de grafo em tempo de autorização não é aceito.

## O que fica fora do hot path

| Componente | Onde pode ser usado | Por quê |
|---|---|---|
| AutoML (Azure ML) | Offline: candidatos, featurização, SHAP, champion/challenger | Chamada remota em autorização é proibida; o serviço consome apenas artefatos aprovados, versionados e em cache |
| Modelos de sequência (GRU/transformer sobre últimas N transações) | Challenger em shadow ou validador assíncrono na trilha de challenge | Custo e variabilidade de latência incompatíveis com o fast path |
| Autoencoder / Isolation Forest global para fraude nova | Shadow e análise offline | Ganho não comprovado no hot path; risco de instabilidade de escore |
| LLMs e agentes de IA | Trilha de challenge assíncrona, após os controles determinísticos | Não substituem hard rules nem política determinística |

## Consequências

- A explicabilidade melhora sem custo de latência: HBOS entrega contribuições por feature de
  graça, e a consolidação determinística (ou logística) mantém pesos legíveis.
- Passam a existir dois modelos supervisionados em produção (global e cold start), o que dobra
  a superfície de monitoramento, versionamento e promoção. É custo aceito em troca de
  calibração adequada na coorte de maior exposição.
- A calibração se torna dependência de release: publicar modelo sem calibração compatível deve
  falhar a validação de schema descrita em [ADR-0004](0004-publicacao-de-modelos-e-cache.md).

## Critérios de aceite

- Nenhuma decisão final tem `camada_que_encerrou = HBOS` sem reason code de política
  explicitamente documentada.
- Toda inferência registra versão do modelo **e** versão da calibração usadas.
- Curva de calibração (reliability) dentro de tolerância definida em janela móvel, com alerta de
  deriva ativo.
- Reason codes derivados das contribuições do HBOS disponíveis para 100% das decisões em que o
  HBOS foi executado.
- Modelo de cold start avaliado por coorte de tempo de relacionamento, com FPR e recall
  comparados aos do modelo global na mesma coorte.
- Nenhum artefato de modelo é promovido com base em métrica isolada; conjunto completo em
  [MLOps](../mlops/dados-rotulos-e-promocao.md).
- Testes de contrato garantindo que o serviço de autorização não realiza chamadas de rede a
  serviços de AutoML ou LLM durante o fast path.
