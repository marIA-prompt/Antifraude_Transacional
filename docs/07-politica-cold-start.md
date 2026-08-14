# 07 — Política de cold start

Prioridade 3.

## AS-IS

CPF novo tende a ser aprovado para reduzir atrito. HBOS individual não tem
histórico útil. No fluxo técnico AS-IS, se a Regra 83 não dispara, o CPF novo
pode ser aprovado **sem** XGBoost.

## Lacuna / risco

Exposição a fraude em alto valor / first transaction. HBOS com perfil vazio
pode ser instável se executado mesmo assim.

## TO-BE

Política **configurável sem redeploy** (arquivo/config service), por valor,
canal, produto, tipo de transação, hard rules e confiança disponível.

Exemplo canônico (valores ilustrativos, não calibrados):

| Condição | Decisão | Reason code |
| --- | --- | --- |
| CPF novo + baixo valor + sem hard rule crítica | `approve` com monitoramento | `cold_start_low_value_monitor` |
| CPF novo + valor intermediário | `challenge` + step-up | `cold_start_step_up` |
| CPF novo + alto valor ou hard rule crítica | `deny` ou `escalate` | `cold_start_high_value` / `cold_start_hard_rule` |

Pesos:

```text
CPF novo → peso HBOS = 0 (ou reduzido)
         → maior peso do XGBoost global
         → reason code cold_start sempre presente
```

Histórico insuficiente (não só CPF nunca visto) usa a mesma política com
`thin_file` em vez de `new_cpf`.

## Critérios de aceite

- Métricas separadas: CPF novo vs CPF com histórico.
- Taxas de fraude, challenge, deny, aprovação legítima e reversão por coorte.
- Thresholds alteráveis sem redeploy (teste de config hot-reload no simulador).
- Revisão periódica de atrito, receita e perda por fraude (processo, não código).
- Testes: `tests/test_cold_start.py`.
