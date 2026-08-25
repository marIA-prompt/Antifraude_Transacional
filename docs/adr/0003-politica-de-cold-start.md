# ADR-0003 — Política de cold start

- **Status:** aceito (revisado em 2026-08-25)
- **Depende de:** [ADR-0001](0001-topologia-de-decisao.md), [ADR-0002](0002-papeis-dos-modelos.md)
- **Lacuna endereçada:** L3 (cold start indefinido)
- **Nota MAPA:** a Etapa 7 do [acompanhamento](../mlops/acompanhamento-modelagem.md) só
  fecha a forma funcional dos pesos depois das Etapas 1–6. Este ADR fixa a **política
  operacional mínima** exigida pelo briefing; não fecha o modelo dedicado de cold start.

## Contexto

### AS-IS

Um CPF novo não possui bundle HBOS confiável: o modelo individual treina sobre o histórico
do próprio cliente. O XGBoost global é a linha que cobre CPF novo. O caminho exato (peso do
HBOS, default de aprovação, reason code) **não está documentado como política configurável**.

### Lacuna/Risco

Aprovação padrão de CPF novo concentra exposição onde não há sinal comportamental. Endurecer
sem faixa de valor penaliza aquisição — é a coorte de maior risco de viés. Alimentar o HBOS
com histórico insuficiente produz anomalia espúria (score alto por falta de base, não por
fraude).

Thresholds `R$ X` e `R$ Y` são parâmetros de negócio, não constantes deste ADR.

## Decisão

**1. Política mínima, configurável, por valor e hard rule** — texto do briefing:

```text
CPF novo + valor < R$ X + sem hard rule
  → approve com monitoramento reforçado

CPF novo + R$ X ≤ valor < R$ Y
  → challenge com step-up

CPF novo + valor ≥ R$ Y  ou  hard rule crítica
  → deny ou escalate
```

**2. Em qualquer caso de CPF novo:**

- peso do HBOS = 0 (ou reduzido por baixa confiança);
- peso do modelo global aumentado;
- reason code obrigatório: `cold_start`.

**3. `R$ X` e `R$ Y` são configuração versionada**, alterável sem redeploy, com trilha de
quem alterou o quê. Valores iniciais são definidos pela operação de fraudes e revisados com
as métricas da coorte — não neste documento.

**4. Modelo dedicado de cold start (GBDT sem features de histórico do CPF) fica adiado**
até o MAPA concluir Etapas 1–6 e a Fase 1 (challenge com desfecho) estar operacional.
Endurecer a coorte sem fila de triagem cria volume sem desfecho, pior do que o AS-IS.

**5. Coorte mensurada em separado.** CPF novo não se mistura ao dashboard geral de FPR/FNR.

## Consequências

- Existe caminho testável para CPF novo, sem comportamento implícito do carregador de
  bundles.
- Aumento de `challenge` na faixa `[X, Y)` pressiona a fila — por isso a trilha de challenge
  (Fase 1) precede o endurecimento.
- Custo de monitoramento: uma coorte a mais, com reason code como chave de reconstituição.

## Critérios de aceite

- Reason code `cold_start` em **100%** das decisões em que a política foi aplicada.
- Peso efetivo do HBOS registrado por transação; = 0 na faixa `sem_historico` (ou o valor
  reduzido configurado, nunca o peso pleno).
- Métricas separadas para a coorte de CPF novo: taxa de fraude confirmada, challenge, deny,
  aprovação legítima, reversão após step-up.
- `X` e `Y` alteráveis sem redeploy, versionados, auditáveis.
- Nenhum `deny` de CPF novo baseado **somente** em score HBOS (peso 0). Hard rule crítica
  continua soberana.
- Revisão periódica documentada de atrito, receita e perda por fraude na coorte, com decisão
  de manter ou ajustar `X`/`Y`.
