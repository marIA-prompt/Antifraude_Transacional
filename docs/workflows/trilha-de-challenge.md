# Trilha de challenge: fila, validadores e step-up

Esta é a **evolução prioritária 1**. Contrato de entrada:
[`fraud.challenge.created`](../contratos/evento-challenge.md).

## Contexto

### AS-IS

A banda `challenge` é produzida pela decisão online, mas não tem desfecho operacional
garantido. O único fluxo operacional existente é a confirmação de compra via WhatsApp no produto
private label, acionada pela Regra 83: confirmação do cliente aprova, ausência de confirmação
nega.

### Lacuna/Risco

Quatro problemas distintos:

1. **Casos sem desfecho.** Uma transação pode ser classificada como questionável sem acionar
   fila, step-up, análise humana, validação adicional ou notificação.
2. **Step-up acoplado à regra e ao produto.** O mecanismo de WhatsApp está preso à Regra 83 e ao
   private label, não à banda de challenge do escore consolidado. Não é reutilizável pelas
   demais trilhas.
3. **Não-resposta tratada como negação.** "Cliente não respondeu" e "cliente negou a compra" são
   sinais muito diferentes — o primeiro é frequentemente atrito (celular sem bateria, notificação
   não vista), o segundo é fraude confirmada pelo próprio titular. Colapsar os dois em `deny`
   gera falso positivo e, pior, contamina os rótulos de treino com fraude que não existiu.
4. **Ausência de idempotência comprovada.** Sem chave de idempotência, reentrega de mensagem
   pode disparar notificação duplicada ao cliente.

## TO-BE

```text
challenge
→ evento fraud.challenge.created
→ persistência de contexto e evidências da decisão inicial
→ fila de triagem
→ workflow de validadores (Agent Framework Workflows)
     ├── validador de regras adicionais       → deny de alta confiança encerra
     ├── validador de blocklist / bureau      → deny de alta confiança encerra
     ├── validador de geolocalização/dispositivo
     ├── validador de histórico estendido
     └── step-up de autenticação (inclui confirmação via WhatsApp)
→ consolidação
→ approve / deny / escalate
→ escalate → fila de análise humana
→ notificação idempotente
→ auditoria
```

O Microsoft Agent Framework Workflows é usado **apenas nesta trilha**, nunca no fast path de
autorização. Não está em produção hoje; é evolução planejada.

## Contrato de cada validador

Requisitos que valem para todos, sem exceção:

- contrato de entrada e saída **versionado**;
- retorna `approve`, `deny` ou `escalate` — nunca um veredito ambíguo;
- retorna evidências e reason codes;
- possui **timeout** e **circuit breaker**;
- possui **fallback seguro** definido: qual resultado assume quando a dependência falha;
- gera tracing, logs e métricas de duração, resultado, erro, timeout e fallback;
- é testável isoladamente, com dependências externas mockáveis;
- **não bloqueia indefinidamente** uma decisão.

Sobre o fallback seguro: "seguro" não significa sempre `deny`. Negar por indisponibilidade de
bureau transforma uma falha de infraestrutura em perda de receita e em rótulo de fraude falso.
A regra padrão é **`escalate` em caso de falha ou timeout**, reservando `deny` automático para
os casos em que a própria ausência de resposta é sinal de risco definido por política explícita.

### Encerramento antecipado

Um validador pode encerrar o workflow apenas com `deny` de **alta confiança** (blocklist
confirmada, bureau com fraude registrada). `approve` de validador não encerra o workflow: os
demais validadores continuam, porque nesta trilha o custo de latência não é restrição e o valor
de acumular evidência é alto. É a mesma lógica do [ADR-0001](../adr/0001-topologia-de-decisao.md)
aplicada ao fluxo assíncrono.

### Step-up de autenticação

O disparo de confirmação via WhatsApp é absorvido como **um validador de step-up**, desacoplado
da Regra 83 e do private label. Semântica dos desfechos:

| Resposta do cliente | Resultado do validador |
|---|---|
| Confirma a compra | `approve` (com registro para monitoramento posterior) |
| Nega a compra | `deny` de alta confiança, mais sinal forte de fraude para rotulagem |
| Não responde até o timeout | `escalate` para análise humana — **nunca `deny` automático** |

A distinção entre negação explícita e silêncio precisa sobreviver até a base de rótulos, porque
alimenta o treino dos modelos supervisionados.

## Checkpoints e retomada de estado

Integrações externas lentas e o step-up (que depende do tempo de resposta humana) exigem que o
workflow suporte **checkpoint e retomada**. O caso não fica com thread ou conexão presa
aguardando; o estado é persistido e retomado quando a resposta chega ou quando o timeout expira.

## Idempotência

Chave: `transaction_id` + `correlation_id`, transportada em `idempotency_key` no evento.
Garantias exigidas:

- reentrega do evento não cria segundo caso na fila;
- validador não é reexecutado para o mesmo caso e mesma versão de contrato;
- notificação ao cliente não é enviada em duplicidade, mesmo com reentrega ou retomada de
  checkpoint;
- consolidação é determinística: mesmas saídas de validadores produzem o mesmo desfecho.

## Agentes de IA nesta trilha

Entram **por último**, como apoio à triagem, e somente depois de os controles determinísticos
estarem operando. Restrições:

- não substituem hard rules nem políticas determinísticas em decisões críticas;
- não decidem sozinhos: produzem sumarização, priorização e hipóteses para o analista humano;
- sujeitos aos mesmos requisitos dos demais validadores (timeout, circuit breaker, fallback,
  tracing, contrato versionado);
- saída registrada como evidência atribuída ao agente, distinguível de evidência determinística
  na auditoria.

## Métricas

- taxa de `challenge` sobre o total de transações;
- desfecho da trilha: aprovação posterior, negação posterior, escalonamento humano;
- **taxa de não-resposta ao step-up, medida separadamente da taxa de negação explícita**;
- tempo até desfecho (p50, p95) e tempo de permanência na fila humana;
- por validador: duração, taxa de erro, taxa de timeout, acionamento de circuit breaker, uso de
  fallback;
- taxa de reversão pós-step-up e pós-análise humana, por coorte;
- casos sem desfecho após o prazo definido (deve ser zero).

## Critérios de aceite

- 100% dos casos `challenge` possuem desfecho rastreável.
- Toda decisão da trilha registra evidências e reason codes.
- Cada validador registra duração, resultado, erro, timeout e fallback.
- O fluxo é idempotente por `transaction_id` e `correlation_id`, comprovado por teste de
  reentrega e de retomada de checkpoint.
- Não-resposta ao step-up resulta em `escalate`, não em `deny`, verificado por teste.
- Negação explícita e não-resposta são persistidas como categorias distintas e chegam distintas à
  base de rótulos.
- Nenhuma notificação duplicada ao cliente sob reentrega de evento.
- Falha de dependência externa não bloqueia o caso além do timeout configurado.
- Taxa de `challenge`, aprovação posterior, negação posterior e escalonamento humano monitoradas
  em dashboard.
