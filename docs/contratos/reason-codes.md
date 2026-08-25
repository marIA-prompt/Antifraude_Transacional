# Catálogo de reason codes

Códigos estáveis, auditáveis e mapeáveis para texto ao titular quando expostos em
atendimento. Incluir código novo exige linha nesta tabela e, se viajar em contrato,
atualização de exemplos.

| Code | Camada | Quando | Texto interno | Exposição ao titular |
|---|---|---|---|---|
| `cold_start` | política | CPF novo / histórico insuficiente | política de cold start aplicada; peso HBOS reduzido ou zero | revisão de cadastro / primeira compra em análise |
| `hbos_unavailable` | fallback | cache miss e timeout PG > 20 ms | bundle HBOS indisponível no fast path | (não expor) decisão por demais camadas |
| `xgb_unavailable` | fallback | falha do XGBoost | fail-safe da cascata: HBOS + regras | (não expor) |
| `viagem_impossivel` | hard rule | deslocamento incompatível com o intervalo | veto geográfico | transação incompatível com o padrão de uso |
| `valor_acima_padrao` | regra / sinal | valor fora do perfil | sinal de valor | valor fora do habitual |
| `estabelecimento_novo` | regra / sinal | merchant novo para o titular | sinal de merchant | estabelecimento ainda não usado por você |
| `hbos_deny_short_circuit` | cascata | HBOS = deny, XGBoost não executado | short-circuit de anomalia — **não** redigir como fraude | transação fora do seu padrão recente |
| `shadow_evaluation` | telemetria | amostra 1%–5% | não afeta decisão online | (nunca expor) |

Códigos de NEG83 / Motor H **não** entram neste catálogo do microserviço de score até D-3
estar fechado. O estudo Motor H tem target e schema próprios.

## Critério de aceite

- 100% das decisões, regras e fallbacks com code desta tabela ou extensão versionada.
- Nenhuma redação ao titular contendo "fraude confirmada pelo HBOS".
- Teste de contrato: eventos de exemplo usam apenas codes conhecidos ou o prefixo documentado.
