# Trilha de challenge: fila, validadores e step-up

**Evolução prioritária 1.** Contrato de entrada:
[`fraud.challenge.created`](../contratos/evento-challenge.md). Agent Framework Workflows
**não está em produção** — é o orquestrador proposto desta esteira, nunca do fast path.

## AS-IS

A banda `challenge` é produzida pela decisão online e **não tem desfecho operacional
garantido**. Existe, em fonte aparte, confirmação de compra via WhatsApp associada a NEG83
no produto private label ([Motor H](../recuperacao/motor-h-neg83.md), D-3 aberto). Não
afirmar que esse WhatsApp é o desfecho do `challenge` deste microserviço até D-3 fechar.

## Lacuna/Risco

1. Caso questionável sem fila, step-up, humano ou notificação.
2. Se o WhatsApp de NEG83 for o único step-up: acoplado a uma regra e a um produto; não
   reutilizável pela banda de escore.
3. Não-resposta tratada como negação mistura atrito com fraude e contamina rótulos.
4. Sem idempotência, reentrega notifica o cliente duas vezes.

## TO-BE

```text
challenge
→ evento fraud.challenge.created
→ persistência de contexto e evidências da decisão inicial
→ fila de triagem
→ workflow de validadores (Agent Framework Workflows)
     ├── validador de regras adicionais
     ├── validador de blocklist / bureau
     ├── validador de geolocalização/dispositivo
     ├── validador de histórico estendido
     └── step-up de autenticação
→ consolidação
→ approve / deny / escalate
→ escalate → fila de análise humana
→ notificação idempotente
→ auditoria
```

Validadores externos **nunca** no caminho síncrono de autorização (critério 10 do briefing).

### Contrato de cada validador

- entrada/saída versionadas;
- retorna `approve`, `deny` ou `escalate` — nunca veredito ambíguo;
- evidências e reason codes;
- **timeout** e **circuit breaker**;
- **fallback seguro** declarado — padrão: `escalate` em falha/timeout; `deny` automático só
  com política explícita (ausência como sinal de risco);
- tracing, duração, resultado, erro, timeout, fallback;
- testável com dependências mockáveis.

`approve` de um validador **não** encerra o workflow. `deny` de alta confiança (blocklist
confirmada, bureau com fraude registrada) pode encerrar.

### Step-up

| Resposta do cliente | Resultado |
|---|---|
| Confirma a compra | `approve` (com monitoramento posterior) |
| Nega a compra | `deny` de alta confiança + sinal forte para rotulagem |
| Não responde até o timeout | `escalate` — **nunca `deny` automático** |

Negação explícita e silêncio chegam distintos à base de rótulos.

Se o canal for WhatsApp hoje usado em NEG83, absorvê-lo como validador **desacoplado** da
regra e do private label — depois de D-3.

### Idempotência

Chave: `transaction_id` + `schema_version` (`idempotency_key` do evento). Reentrega não
duplica caso, validador nem notificação.

### Agentes de IA

Entram por último, depois dos controles determinísticos. Não substituem hard rules. Não
decidem sozinhos. Mesmos requisitos de timeout, circuit breaker, fallback e contrato.

## SLOs do caminho de análise

| Métrica | Alvo |
|---|---|
| Workflow de challenge (p95) | < 3 s síncrono / < 60 s assíncrono |
| Timeout por validador interno | 800 ms |
| Timeout por validador externo (bureau) | 2 s |
| Taxa de fallback por validador | < 1% |
| Tempo até desfecho de step-up (mediana) | < 5 min |
| Backlog da fila de triagem humana | < 30 min |
| `escalate` sem tratamento em 24 h | 0% |
| Challenges com desfecho rastreável | 100% |

`ttl_seconds` do evento: **900** (15 min) para conciliação de caso órfão — distinto do SLO
de step-up (mediana < 5 min) e do escalate em 24 h.

## Critérios de aceite

- 100% dos `challenge` com desfecho rastreável.
- SLOs da tabela em dashboard, com alerta quando qualquer linha estourar.
- Idempotência comprovada por teste de reentrega e de retomada de checkpoint.
- Não-resposta → `escalate`, verificado por teste.
- Negação e não-resposta persistidas como categorias distintas até os rótulos.
- Zero notificação duplicada sob reentrega.
- Falha externa não bloqueia além do timeout (800 ms / 2 s).
- Taxa de fallback por validador < 1%.
- `escalate` sem tratamento em 24 h = 0%.
