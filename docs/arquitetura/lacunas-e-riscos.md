# Registro de lacunas e riscos

Cada item declara evidência (o que no AS-IS sustenta o risco), impacto e a evolução que o endereça.
Severidade: **Alta** = perda financeira, exposição regulatória ou decisão sem rastro;
**Média** = degradação de qualidade ou de operação; **Baixa** = dívida controlável.

| ID | Lacuna / Risco | Severidade | Evidência no AS-IS | Impacto | Endereçado por |
| --- | --- | --- | --- | --- | --- |
| LR-01 | `challenge` sem ação operacional | Alta | Faixa intermediária existe na decisão; diagrama termina em `challenge` sem destino | Caso questionável fica sem desfecho: nem atrito, nem proteção. Perda por fraude aceita silenciosamente ou cliente legítimo travado sem tratativa | [Evolução 1](../evolucoes/01-challenge-operacional.md) |
| LR-02 | Contrato HTTP expõe apenas `decision_final` | Alta | Especificação prevê 5 campos; implementação retorna 1 | Explicabilidade indisponível a consumidores legítimos; contestação e auditoria dependem de log; orquestração tentada sobre resposta HTTP tende a acoplar-se ao hot path | [Evolução 1](../evolucoes/01-challenge-operacional.md) + [contratos](../contratos/README.md) |
| LR-03 | Cache de modelo sem invalidação após retreino | Alta | Bundles servidos por cache em memória; publicação exige restart ou limpeza manual | Serviço decide com modelo antigo sem sinalizar; rollback e correção de incidente dependem de intervenção manual; inferência sem versão registrada é irreprodutível | [Evolução 2](../evolucoes/02-publicacao-de-modelos-e-cache.md) |
| LR-04 | Viés de seleção do short-circuit e do gate de regra 83 | Alta | Regra 83 filtra a entrada do motor; short-circuit suprime camadas posteriores | Modelos treinam e são avaliados sobre população selecionada por regra determinística. Performance das camadas suprimidas é inobservável e o retreinamento herda o viés da regra | [Observabilidade e shadow](../mlops/observabilidade-e-shadow.md) |
| LR-05 | Aprovação padrão de CPF novo | Alta | Ausência de histórico torna o HBOS inaplicável; default é aprovar | Vetor direto de fraude em conta nova e teste de cartão; HBOS com peso indevido gera anomalia espúria por falta de base | [Evolução 3](../evolucoes/03-cold-start.md) |
| LR-06 | Step-up por WhatsApp sem política declarada | Média | Diagrama do produto nega a compra quando o cliente não confirma | "Não confirmado" agrega recusa deliberada, indisponibilidade de canal, número desatualizado e timeout. Tratar tudo como fraude gera falso positivo e exclusão de cliente sem device/canal ativo | [Evolução 1](../evolucoes/01-challenge-operacional.md) |
| LR-07 | Rótulos imaturos tratados como legítimos | Alta | Fraude pode ser confirmada dias ou semanas depois | Rotular `sem_desfecho` como legítimo ensina o modelo a aprovar fraude ainda não contestada e infla artificialmente a precisão medida | [Dados e rótulos](../mlops/dados-e-validacao-temporal.md) |
| LR-08 | Risco de leakage temporal | Alta | Features derivadas de histórico e de status pós-transação | Métricas offline otimistas que não se reproduzem online; decisão de promoção baseada em ganho inexistente | [Dados e rótulos](../mlops/dados-e-validacao-temporal.md) |
| LR-09 | HBOS interpretado como prova de fraude | Média | Score alto = atipicidade; risco de leitura como fraude | Negação de cliente legítimo com comportamento variável e reason code enganoso em contestação | [TO-BE](to-be.md) + [viés](../mlops/vies-e-equidade.md) |
| LR-10 | Amplificação de sinais correlacionados | Média | Mesma evidência pode pesar em regra, HBOS e XGBoost | Risco somado mais de uma vez pela mesma causa raiz; efeito concentrado em coortes específicas | [Viés e equidade](../mlops/vies-e-equidade.md) |
| LR-11 | Divergência não resolvida sobre a ordem da cascata | Média | Divergências D-1 a D-3 em [as-is.md](as-is.md) | Impossível atribuir decisão a camada, calibrar thresholds ou auditar sem trace por camada | [Observabilidade e shadow](../mlops/observabilidade-e-shadow.md) |
| LR-12 | Dado pessoal em log e evento | Alta | Score, features e contexto trafegam em logs internos | Exposição de CPF e comportamento além da finalidade; retenção indefinida; risco LGPD | [LGPD](../governanca/lgpd-e-dados-sensiveis.md) |
| LR-13 | Exposição da lógica antifraude | Média | API com explicabilidade é evolução desejada | Reason code detalhado devolvido a canal não confiável ensina o fraudador a burlar regra e threshold | [Contratos](../contratos/README.md) + [LGPD](../governanca/lgpd-e-dados-sensiveis.md) |
| LR-14 | Thresholds acoplados a deploy | Média | Não há evidência de configuração dinâmica | Resposta a ataque em curso ou a falso positivo em massa depende de release | [Evolução 3](../evolucoes/03-cold-start.md) |
| LR-15 | Ausência de fallback declarado por camada | Média | Cache, bureau e device intelligence podem falhar | Sem política explícita, indisponibilidade externa vira negação em massa (fail-closed acidental) ou aprovação cega (fail-open acidental) | [TO-BE](to-be.md) |
| LR-16 | Risco de AutoML no hot path | Alta | AutoML é evolução planejada, com uso restrito a offline | Chamada remota em autorização quebra o p95 de 100 ms e cria dependência externa não controlada no caminho crítico | [Promoção e rollout](../mlops/promocao-e-rollout.md) |

## Ordem de ataque

A sequência não é negociável por dependência técnica, não por preferência:

1. **Instrumentação de decision trace** (LR-11, LR-04). Sem saber qual camada decide, calibrar
   `challenge` é chute e nenhum critério de aceite é verificável.
2. **Operacionalizar `challenge`** (LR-01, LR-02, LR-06). É onde está a perda concreta.
3. **Publicação de modelo e invalidação de cache** (LR-03). Habilita qualquer ciclo de melhoria de
   modelo com rollback real.
4. **Cold start** (LR-05, LR-14). Depende de thresholds dinâmicos e de métricas por coorte.
5. **Agentes de IA na triagem** — somente após 1 a 4, e sempre depois dos controles determinísticos.
