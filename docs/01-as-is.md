# 01 — AS-IS: o que existe e está documentado

Este documento descreve apenas o estado atual, com base no contexto operacional
e nos três fluxogramas de referência. Não mistura evolução planejada.

## Papel do sistema

Microserviço de **score antifraude online** para transações de cartão private
label. A decisão síncrona de autorização ocorre em baixa latência, com
short-circuit entre camadas.

Meta de performance documentada:

```text
Fast path de approve/deny: p95 < 100 ms
```

## Fluxo textual documentado

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

## Componentes de decisão em produção (documentados)

### HBOS individual por CPF

| Atributo | AS-IS |
| --- | --- |
| Tipo | Não supervisionado, detecção de anomalia |
| Granularidade | Um modelo por CPF, treinado offline |
| Comparação | Transação atual vs histórico do próprio cliente (~730 dias) |
| Artefato | Bundle com modelo, scaler, perfis estatísticos e metadados |
| Serving | Cache em memória |
| Interpretação | Score alto = comportamento atípico, **não** prova de fraude |

### XGBoost global

| Atributo | AS-IS |
| --- | --- |
| Tipo | Supervisionado, rótulos históricos fraude / não fraude |
| Papel | Padrões globais e interações entre features |
| Complemento | Especialmente útil para CPF novo ou histórico insuficiente |
| Dependência | Qualidade, maturação e representatividade dos rótulos |

### Regras de negócio e hard rules

Regras determinísticas avaliam horário, valor, parcelas, estabelecimento novo,
geolocalização, device intelligence, blocklists e viagem impossível. Hard rules
críticas podem prevalecer sobre scores probabilísticos. Toda regra deve gerar
evidência e reason code — este requisito está documentado, mas a completude da
evidência na resposta HTTP não está garantida (ver [02](02-lacunas-e-riscos.md)).

## Fluxograma operacional do cartão (visão de produto)

Fluxo de compra private label observado:

```text
Cartão private label
→ transação de compra
→ autenticador (saldo, senha, etc.)
    não autenticado → compra negada
→ autenticado → Inteligência Artificial
    → Regras de Antifraude (nome: 83)
        Não → compra aprovada
        Sim → disparo de confirmação via WhatsApp
            confirmado pelo cliente → compra aprovada
            não confirmado → compra negada
```

Nesta visão, a **Regra 83** é o gatilho operacional de challenge (WhatsApp).
HBOS e XGBoost não aparecem explicitamente no desenho de produto.

## Fluxograma técnico da cascata (visão de motor)

```text
TRANSAÇÃO
→ Caiu na Regra 83?
    NÃO → APROVADO
    SIM → MOTOR HBOS
        APROVADO → fim
        REPROVADO ─┐
        CHALLENGE ─┴→ XGBOOST
                        APROVADO | REPROVADO | CHALLENGE
```

Nesta visão:

- a Regra 83 é um **pré-filtro**: transação fora da regra é aprovada sem HBOS/XGBoost;
- o XGBoost só refina casos que o HBOS marcou como `REPROVADO` ou `CHALLENGE`;
- `CHALLENGE` existe como faixa de decisão do motor.

## Contrato HTTP

### Especificação original do microserviço

Cinco saídas estruturadas:

```json
{
  "score": 0.0,
  "decision": "approve | challenge | deny",
  "signals": [],
  "features": {},
  "feature_weights": {}
}
```

### Implementação observada na apresentação mais recente

```json
{
  "decision_final": "approve | challenge | deny"
}
```

Score, sinais, features e pesos permanecem em logs ou eventos internos, não na
resposta HTTP v1.

## O que **não** está em produção

Os itens abaixo são evoluções planejadas e **não** devem ser descritos como AS-IS:

- Azure Machine Learning AutoML no ciclo operacional;
- Microsoft Agent Framework Workflows;
- orquestração completa de `challenge` (fila, validadores, escalate, auditoria de desfecho);
- API v2 de explicabilidade;
- publicação atômica de modelo com invalidação de cache sem restart;
- política de cold start configurável por valor/canal/produto;
- shadow sampling de 1% a 5% em todas as camadas.

## Síntese AS-IS

O motor decide `approve | challenge | deny` em cascata, com Regra 83 como
filtro relevante, HBOS como sinal de anomalia individual, XGBoost como
refinamento supervisionado e WhatsApp como único tratamento operacional
visível de challenge no fluxo de produto. A resposta síncrona ao autorizador
expõe apenas `decision_final`.
