# Catálogo de reason codes

Toda decisão, regra acionada, fallback e desfecho de `challenge` carrega pelo menos um reason code
deste catálogo. Formato: `RC_` seguido de letras maiúsculas, dígitos e `_` (`^RC_[A-Z0-9_]{2,48}$`),
validado por schema.

A coluna **Exposição** define o que pode sair do serviço, por perfil de consumidor
(ver [LGPD](../governanca/lgpd-e-dados-sensiveis.md)): `interno` nunca é devolvido a canal externo;
`externo` é seguro para cliente porque não revela regra nem threshold.

## Decisão e estrutura da cascata

| Código | Significado | Camada | Exposição |
| --- | --- | --- | --- |
| `RC_APPROVE_LOW_RISK` | Risco abaixo da faixa de atrito | `decision_consolidation` | externo |
| `RC_NOT_ELIGIBLE_FOR_SCORING` | Gate de elegibilidade não acionou o motor de modelos | `eligibility_gate` | interno |
| `RC_RULE_83_TRIGGERED` | Regra 83 acionada; transação segue para o motor | `eligibility_gate` | interno |
| `RC_INTERMEDIATE_RISK` | Faixa intermediária: origem do `challenge` | `decision_consolidation` | interno |
| `RC_HIGH_CONSOLIDATED_RISK` | Score consolidado na faixa alta | `decision_consolidation` | interno |
| `RC_PAYLOAD_INVALID` | Payload rejeitado na validação | `payload_validation` | externo |

## Hard rules e regras de negócio

| Código | Significado | Severidade típica | Exposição |
| --- | --- | --- | --- |
| `RC_BLOCKLIST_HIT` | CPF, device, cartão ou estabelecimento em blocklist | `hard_block` | interno |
| `RC_IMPOSSIBLE_TRAVEL` | Deslocamento incompatível entre transações | `hard_block` | interno |
| `RC_VELOCITY_BREACH` | Tentativas acima do limite na janela | `hard_review` | interno |
| `RC_AMOUNT_OUT_OF_PROFILE` | Valor fora do perfil do cliente | `soft` | interno |
| `RC_NEW_MERCHANT` | Estabelecimento novo para o titular | `soft` | interno |
| `RC_ODD_HOUR` | Horário atípico para o titular | `soft` | interno |
| `RC_INSTALLMENTS_ATYPICAL` | Parcelamento fora do padrão | `soft` | interno |
| `RC_GEO_INCONSISTENT` | Geolocalização divergente do histórico | `soft` | interno |
| `RC_DEVICE_NEW` | Dispositivo não reconhecido | `soft` | interno |

## Modelos

| Código | Significado | Observação |
| --- | --- | --- |
| `RC_HBOS_ANOMALY_HIGH` | Comportamento atípico frente ao histórico do próprio CPF | Sinal comportamental; **não** é prova de fraude e não sustenta `deny` isolado |
| `RC_HBOS_UNAVAILABLE` | Bundle ausente ou não carregado | Peso redistribuído; decisão segue sem o sinal |
| `RC_XGB_HIGH_RISK` | Modelo global aponta risco alto | Depende de rótulo maduro e validação temporal |
| `RC_MODEL_UNAVAILABLE` | Modelo indisponível ou em timeout | Faixa intermediária resolve para `challenge` |
| `RC_FEATURE_MISSING` | Feature não disponível em tempo de decisão | Tratada como desconhecida, nunca como benigna |

## Cold start

| Código | Significado |
| --- | --- |
| `RC_COLD_START` | Confiança de histórico `none` ou `low`; peso do HBOS reduzido ou nulo |
| `RC_COLD_START_LOW_VALUE_APPROVED` | Aprovação com monitoramento reforçado |
| `RC_COLD_START_STEPUP_REQUIRED` | `challenge` com step-up por faixa de valor |
| `RC_COLD_START_HIGH_VALUE_BLOCKED` | `deny` ou `escalate` por valor alto ou hard rule crítica |
| `RC_CUMULATIVE_LOW_VALUE_LIMIT` | Limite acumulado da janela atingido (antifracionamento) |

## Step-up

| Código | Significado | Não confundir com |
| --- | --- | --- |
| `RC_STEPUP_CONFIRMED` | Cliente confirmou a compra | — |
| `RC_STEPUP_DENIED` | Cliente negou a compra | — |
| `RC_STEPUP_TIMEOUT` | Sem resposta na janela | Negação pelo cliente |
| `RC_STEPUP_UNREACHABLE` | Canal indisponível ou contato inválido | Negação pelo cliente |

## Trilha assíncrona de challenge

| Código | Significado |
| --- | --- |
| `RC_VALIDATOR_DENY_HIGH_CONFIDENCE` | Validador encerrou a cadeia com negação de alta confiança |
| `RC_BUREAU_NEGATIVE` | Retorno negativo de bureau |
| `RC_BLOCKLIST_UNAVAILABLE` | Blocklist indisponível; fail-closed na faixa alta |
| `RC_EXTERNAL_TIMEOUT` | Integração externa excedeu o timeout |
| `RC_CIRCUIT_OPEN` | Circuit breaker aberto; fallback seguro aplicado |
| `RC_CACHE_DEGRADED` | Cache distribuído indisponível; versão local mantida |
| `RC_LOW_CONFIDENCE_ESCALATED` | Baixa confiança consolidada; enviado a análise humana |
| `RC_MANUAL_REVIEW_REQUIRED` | Alto impacto exige revisão humana |
| `RC_HUMAN_APPROVED` | Analista aprovou |
| `RC_HUMAN_DENIED` | Analista negou |
| `RC_AI_TRIAGE_HINT` | Apoio de agente de IA registrado como evidência, sem poder de decisão |

## Códigos públicos (canal externo e cliente)

Agregados, sem revelar regra, threshold ou peso (`LR-13`):

| Código | Uso |
| --- | --- |
| `RC_PUBLIC_APPROVED` | Compra aprovada |
| `RC_PUBLIC_CONFIRMATION_REQUIRED` | É necessário confirmar a compra |
| `RC_PUBLIC_DECLINED_SECURITY` | Compra não autorizada por segurança |
| `RC_PUBLIC_UNDER_REVIEW` | Em análise |

## Regras de uso

1. Reason code interno **nunca** é devolvido a canal externo; a v2 aplica o mapeamento por perfil no
   serviço, não no consumidor.
2. Um desfecho sem reason code é inválido e deve ser rejeitado pelo schema — não registrado com
   valor genérico.
3. Fallback sempre gera reason code próprio: indisponibilidade não pode virar decisão silenciosa.
4. Incluir código novo exige entrada neste catálogo, mapeamento de exposição e atualização das
   métricas que agregam por reason code.
