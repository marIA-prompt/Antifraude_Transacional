# Motor H — ranking de recuperação de jornadas NEG83

Fonte: *Motor H — Avaliação de recuperação e exposição da regra NEG83* (Fraudes • IA •
Tecnologia, agosto 2026). Resultados para discussão; não é o motor de score FastAPI.

## AS-IS do estudo

O Motor H **não prevê fraude**. Ordena jornadas NEG83 pela propensão a apresentar sucesso
posterior (`LATER_SUCCESS`): o cliente confirma que reconhece a compra e consegue concluir
a transação depois.

```text
Transação → Autenticador → NEG83 → Bloqueio WhatsApp → Confirmação → Nova tentativa
```

| Aspecto | Valor no estudo |
|---|---|
| Algoritmo | `HistGradientBoostingClassifier` (HGB) |
| Entrada | 33 features de `FIRST_NEG83` |
| Saída | `later_success_score` (ranking, **não** probabilidade calibrada de fraude ou legitimidade) |
| Uso proposto | ordenar episódios e aplicar thresholds de policy |
| Período | teste temporal após calibração por budget na validação |

Jornada com recuperação observada: cliente confirma e conclui depois. Sem recuperação
observada (`NO_LATER_SUCCESS`): heterogênea — desistência, troca de cartão, falha no
WhatsApp ou fraude real.

### Métricas no período de teste (AS-IS do estudo)

| Métrica | Valor |
|---|---|
| ROC AUC test | 0,773 |
| Average Precision | 0,850 |
| `LATER_SUCCESS` no teste | 62,7% |

Há sobreposição entre populações. Conclusão do estudo: ordenação útil, **não existe
threshold sem custo**.

### Policies avaliadas no teste

Calibradas por budget na validação, avaliadas em período futuro.

| Policy | Recuperações | Exposições | Rescue | Volume recuperado | Volume exposto |
|---|---|---|---|---|---|
| H-02 | 69 | 3 | 5,8% | — | — |
| H-05 | 144 | 5 | 12,2% | R$ 63,6 mil | R$ 2,9 mil |
| H-10 | 447 | 61 | 37,8% | R$ 192,2 mil | R$ 20,5 mil |
| H-15 | 602 | 96 | 51,0% | R$ 251,6 mil | R$ 40,5 mil |

Transição H-05 → H-10: +303 recuperações, +56 exposições, +R$ 128,6 mil recuperados,
+R$ 17,6 mil expostos.

**Volume exposto ≠ fraude ou perda financeira.** `NO_LATER_SUCCESS` é ausência de recuperação
observada.

O estudo afirma que já existe API para teste assistido; atuação real só após essa etapa.

## Lacuna/Risco

- Target é recuperação posterior, não `fraude_confirmada`.
- `NO_LATER_SUCCESS` mistura desistência, falha de canal e fraude.
- Ainda não há cruzamento com chargeback, contestação ou perda financeira.
- Threshold fixo pode variar no tempo.
- 33 features de `FIRST_NEG83` **não** são a lista do microserviço de score (D-2: 10 × 13,
  lista não canônica). São problemas e schemas distintos.
- Relação NEG83 × `POST /api/v1/score-transaction` é [D-3](../arquitetura/divergencias-documentais.md):
  aberta.
- Colocar Motor H no hot path de autorização violaria o budget de 15 ms e o papel do
  XGBoost/HBOS ([ADR-0002](../adr/0002-papeis-dos-modelos.md)).

## TO-BE (condicional à aprovação da operação)

```text
Discussão da policy → teste assistido → avaliação operacional
```

Qualquer atuação em produção:

- fora do span síncrono de `score-transaction`;
- policy explícita (candidatas H-05 / H-10 / H-15 ou outra, com budget de exposição);
- cruzamento posterior com chargeback/contestação antes de promover threshold;
- idempotência e não-resposta ao WhatsApp tratadas como na
  [trilha de challenge](../workflows/trilha-de-challenge.md) (`escalate`, não `deny`
  automático — se este step-up for o mesmo canal).

Não-resposta e negação explícita permanecem categorias distintas na rotulagem.

## Critérios de aceite (teste assistido)

- Policy candidata escolhida com teto de exposição financeira explícito (R$) e rescue
  esperado.
- Teste em período futuro, com as mesmas métricas da tabela (recuperações, exposições,
  R$ recuperado, R$ exposto), mais chargeback/contestação quando disponível.
- Score tratado como ranking: não usar `later_success_score` como P(fraude) nem como
  P(legítima).
- Zero chamada ao Motor H no span de autorização do FastAPI (tracing).
- Relatório de estabilidade temporal do threshold (variação semanal de rescue e exposição
  ≥ registrada).
- D-3 resolvido ou, no mínimo, diagrama que posicione Motor H **ao lado** do score, não
  dentro da cascata HBOS/XGBoost.
