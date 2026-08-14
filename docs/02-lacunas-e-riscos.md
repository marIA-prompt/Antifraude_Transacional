# 02 — Lacunas e riscos

Cada item abaixo é uma limitação do AS-IS, não uma afirmação de implementação.

## 1. Três visões da cascata não são equivalentes

| Fonte | Papel da Regra 83 | Papel do HBOS | Papel do XGBoost | Challenge |
| --- | --- | --- | --- | --- |
| Texto operacional | Depois do HBOS, junto das hard rules | Sempre no fluxo documentado | Sempre no fluxo documentado | Faixa de decisão |
| Fluxo de produto | Gatilho único de IA; Sim → WhatsApp | Ausente no desenho | Ausente no desenho | WhatsApp de confirmação |
| Fluxo técnico | Pré-filtro: Não → aprova sem ML | Só se caiu na 83 | Só se HBOS ≠ aprovado | Faixa do HBOS e do XGBoost |

**Risco:** operação, ciência de dados e produto podem estar otimizando fluxos
diferentes. Short-circuit da Regra 83 (aprovar sem ML) gera **viés de seleção**
para retreino: o XGBoost só vê a população que já caiu na regra.

## 2. `challenge` sem ação operacional completa

A faixa intermediária existe na lógica, mas o contexto operacional registra que
não há fluxo completo de fila, step-up genérico, análise humana, validadores
adicionais ou notificação rastreável.

O WhatsApp de confirmação cobre **um** recorte (Regra 83 no fluxo de produto).
Não cobre:

- challenge originado por HBOS/XGBoost fora da Regra 83;
- desfecho `escalate` para fila humana;
- idempotência por `transaction_id` + `correlation_id`;
- evidência de timeout/fallback de cada validador;
- garantia de 100% de desfecho rastreável.

**Risco:** transação classificada como questionável pode ser autorizada,
negada ou ficar em limbo sem trilha auditável.

## 3. Divergência do contrato da API

Consumidores da especificação original esperam `score`, `signals`, `features`
e `feature_weights`. A HTTP atual pode devolver só `decision_final`.

**Risco:**

- orquestrador de challenge acoplado à HTTP v1 não recebe contexto suficiente;
- explicabilidade indisponível para consumidores autorizados;
- tentação de ampliar a v1 e quebrar retrocompatibilidade ou vazar lógica antifraude.

## 4. Cache de modelo sem invalidação automática

Após retreino, instâncias podem continuar servindo artefatos antigos até
restart ou limpeza manual.

**Risco:** decisões com versão defasada, rollback lento, ausência de
`model_version` por inferência, divergência entre instâncias.

## 5. Cold start implícito e permissivo

Aprovação padrão de CPF novo reduz atrito e aumenta exposição. HBOS individual
não é informativo sem histórico, mas o fluxo técnico pode nem executá-lo
(Regra 83) ou executá-lo com perfil vazio.

**Risco:** fraude first-party / account opening / CPF recém-usado em alto valor
passa com o mesmo tratamento de compra recorrente de baixo valor.

## 6. Short-circuit oculta camadas posteriores

O short-circuit protege p95 < 100 ms, mas:

- não registra de forma obrigatória camadas **não** executadas;
- impede medir HBOS/XGBoost na população aprovada cedo;
- enviesa labels e features de retreino.

## 7. Rotulagem e leakage

Fraude madura chega dias/semanas depois. Tratar `sem_desfecho` como legítima
infla falso negativo invertido (modelo aprende a aprovar o que ainda não foi
investigado). Features com informação posterior à transação geram leakage.

## 8. Explicabilidade e LGPD

Pesos e features na borda HTTP sem autorização por perfil podem expor lógica
antifraude e dados pessoais. CPF em claro em eventos de challenge viola
minimização. Ausência de reason code auditável impede contestação e revisão.

## 9. AutoML e agentes ainda não governados em produção

Não estão em produção. O risco futuro é usá-los no hot path ou como substitutos
de hard rules. Isso quebraria latência, determinismo e auditabilidade.

## Mapa rápido

| Prioridade | Lacuna | Impacto |
| --- | --- | --- |
| P0 | Challenge sem desfecho operacional completo | Fraude residual e limbo operacional |
| P0 | Cache de modelo sem publicação atômica | Decisão com artefato errado |
| P0 | Cold start não configurável | Exposição em CPF novo |
| P1 | Contrato HTTP divergente | Integração e explicabilidade |
| P1 | Short-circuit sem shadow | Viés de retreino |
| P1 | Três fluxos da Regra 83 | Governança da cascata |
| P2 | Rotulagem / drift / viés | Qualidade do XGBoost |
