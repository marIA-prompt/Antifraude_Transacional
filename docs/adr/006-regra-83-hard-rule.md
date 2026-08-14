# ADR-006 — Regra 83 como hard rule nomeada

## Status

Aceito

## Contexto

Produto trata a Regra 83 como gatilho de WhatsApp. O motor técnico a usa como
pré-filtro de aprovação. O texto operacional a coloca depois do HBOS. Isso
gera viés de seleção e dualidade operacional.

## Decisão

No TO-BE, a Regra 83 é uma hard rule versionada:

- dispara **sinal** `rule_83_triggered` (não decide sozinha o WhatsApp);
- se a política configurar short-circuit, o motivo e a camada de encerramento
  são gravados;
- transações fora da regra **não** são aprovadas por omissão: seguem
  consolidação;
- WhatsApp é step-up da trilha de challenge, acionável também por outros sinais.

Shadow mode mede o que aconteceria se a 83 ainda fosse pré-filtro absoluto.

## Consequências

- Produto precisa migrar o significado de “caiu na 83”.
- Volume de challenge pode mudar; thresholds são configuráveis sem redeploy.
