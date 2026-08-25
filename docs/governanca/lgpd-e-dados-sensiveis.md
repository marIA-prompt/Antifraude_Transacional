# LGPD, dados pessoais e exposição da lógica antifraude

## AS-IS

O microserviço valida payload com CPF (11 dígitos) e CNPJ (14). A resposta HTTP vigente
expõe só `decision_final`, mas logs de auditoria carregam o detalhe da decisão. Eventos e
filas de challenge **ainda não existem** em produção.

## Lacuna/Risco

- CPF em claro em log, cache, chave de invalidação ou tópico de mensageria amplia a
  superfície além da finalidade (prevenção a fraudes / legítimo interesse).
- Decisões automatizadas de alto impacto (`deny`) sem DPIA e sem reason code inteligível
  inviabilizam o pedido de revisão (art. 20).
- API v2 sem autorização por perfil ensina thresholds e regras a quem não deveria vê-las
  (engenharia reversa da política).
- Retenção única para log de auditoria e payload bruto ignora minimização.

## TO-BE

| Controle | Exigência |
|---|---|
| Base legal | Documentada por finalidade (prevenção a fraudes / legítimo interesse) |
| DPIA | Para decisões automatizadas de alto impacto (`deny` e `escalate`) |
| Titular | Reason codes mapeáveis para explicação; não identificadores internos opacos |
| Tokenização | `cpf_token` (ou `subject_token`) em eventos, logs, filas e chaves de cache. CPF em claro não trafega fora do perímetro de validação do payload, e o TO-BE é tokenizar também a entrada |
| Retenção | Prazo distinto: auditoria de decisão vs payload bruto. A janela de ~730 dias do HBOS é finalidade de **modelagem**, não autorização automática para reter evento operacional o mesmo período |
| API v2 | Autenticação, escopo `antifraude.score.explain`, mascaramento no servidor, rate limiting, trilha de quem consultou o quê |
| Step-up | Notificação ao titular não revela a regra interna acionada |

Chave de cache do HBOS no [ADR-0004](../adr/0004-publicacao-de-modelos-e-cache.md):
`cpf_token + model_version`, nunca o número do CPF.

## Critérios de aceite

- Contratos (`contracts/`) sem campos `cpf`, `cpf_titular`, `document_number`, `taxpayer_id`
  — verificado por `scripts/validate_contracts.py`.
- 100% dos eventos `fraud.challenge.created` com `cpf_token` e sem CPF em claro.
- DPIA publicada antes do primeiro `deny` automatizado que não seja hard rule já existente.
- Catálogo de reason codes com texto de titular para 100% dos códigos expostos em
  atendimento.
- Política de retenção com dois prazos numéricos (dias) e job de expiração testado.
- Acesso à v2 auditado: 100% das consultas com `actor`, `transaction_id`, perfil e timestamp.
