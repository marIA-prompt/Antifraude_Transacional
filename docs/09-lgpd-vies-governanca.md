# 09 — LGPD, viés, explicabilidade e governança

## AS-IS

O motor processa transações ligadas a CPF, comportamento e potencialmente
geolocalização/dispositivo. A HTTP v1 não devolve features, o que reduz
exposição na borda, mas logs internos ainda precisam de base legal e
minimização.

## Lacuna / risco

- CPF em claro em eventos e logs.
- Explicabilidade insuficiente para contestação (art. 20 LGPD / revisão de
  decisão automatizada).
- Viés de seleção da Regra 83 e de rotulagem (mais investigação em certos
  segmentos).
- Geo e tipo de comércio como proxy de atributo protegido.

## TO-BE — controles LGPD

| Controle | Aplicação |
| --- | --- |
| Minimização | Eventos e v2 usam `subject_id` tokenizado |
| Finalidade | Score antifraude de autorização; sem reuso para marketing |
| Base legal | Execução de contrato / proteção ao crédito / prevenção a fraude, documentada no RIPD |
| Acesso | v2 com perfil; logs com retenção definida |
| Titular | Reason codes compreensíveis na contestação, sem revelar regra completa explorável |
| Retenção | Auditoria de decisão com prazo distinto do bundle HBOS (~730 dias de histórico comportamental) |
| Encerramento | Exclusão/anonimização do bundle HBOS do CPF quando aplicável |

Decisão automatizada com efeito relevante (`deny`) deve permitir revisão
humana na trilha de `escalate` / contestação — outro motivo para não deixar
`challenge`/`deny` sem desfecho.

## Viés e equidade

Avaliar o **processo completo**: dados, regras, cascata, short-circuit,
rotulagem e retreino — não só o XGBoost.

Riscos principais:

- CPF novo e thin-file;
- clientes legítimos com comportamento variável (viagem, presente);
- geolocalização desigual entre regiões;
- MCC / tipo de comércio como proxy;
- regras históricas que selecionam quem o modelo vê;
- rótulos que refletem investigação desigual;
- amplificação de sinais correlacionados (HBOS + regra + XGBoost no mesmo fato).

Controles:

- métricas por coorte (relacionamento, volume, canal, região operacional, MCC,
  qualidade de dados) — **não** por atributo protegido direto;
- comparar FPR, FNR, recall, precisão, challenge e deny por coorte;
- peso HBOS reduzido com histórico insuficiente;
- cap de impacto cumulativo de sinais correlacionados;
- revisão humana em baixa confiança ou alto impacto;
- medir reversões após step-up e análise humana.

## Explicabilidade

| Audiência | Nível |
| --- | --- |
| Autorizador | `decision_final` |
| Operação / contestação | reason codes + sinais |
| Ciência de dados | features, pesos, SHAP offline |
| Atacante / público | nada da lógica interna |

SHAP e AutoML feature importance são artefatos **offline**, nunca calculados
sincronamente na transação.

## Critérios de aceite

- Scanner de contratos: nenhum schema de evento possui campo `cpf`.
- v2 mascara identificadores.
- Dashboard de coortes (processo + métricas), não apenas AUC global.
- RIPD / registro de tratamento atualizado antes do go-live da v2 e dos eventos.
