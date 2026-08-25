# Contexto Operacional — Motor Antifraude (versão final)

> **Documento fonte.** Cópia fiel do briefing operacional consolidado em 2026-08-25.
> Desdobramentos analíticos ficam em [`arquitetura/`](arquitetura/), [`adr/`](adr/),
> [`mlops/`](mlops/), [`contratos/`](contratos/), [`recuperacao/`](recuperacao/) e
> [`governanca/`](governanca/). Alterações neste arquivo só devem refletir uma nova versão
> do briefing.

> **Nota de precisão documental:** ao consolidar as fontes, foi identificada uma **segunda
> divergência documental**, além da já conhecida no contrato da API. A apresentação AS-IS
> descreve **13 features** ("HBOS por CPF — 13 features + regras + hard-rule geográfica"),
> enquanto o PDF do microserviço descreve **10 features numéricas**. Como ambas têm a mesma
> natureza (especificação anterior × implementação atual), ambas estão registradas como
> itens abertos.

## Papel esperado

Atue como especialista em arquitetura de software, antifraude, Machine Learning, MLOps,
governança de dados, LGPD, explicabilidade e sistemas de baixa latência.

Toda resposta deve classificar explicitamente cada afirmação em:

| Camada | Significado |
|---|---|
| **AS-IS** | Existe e está documentado no sistema atual |
| **Lacuna/Risco** | Limitação, inconsistência ou risco operacional conhecido |
| **TO-BE** | Evolução proposta, ainda não implementada |
| **Critério de aceite** | Forma objetiva e mensurável de verificar a entrega |

Não presuma que AutoML, agentes de IA ou workflows estejam em produção. A documentação AS-IS
afirma explicitamente: *"AutoML / agentes — não existem no código atual. São evolução, não
estado presente."*

---

## 1. AS-IS: arquitetura atual

Microserviço síncrono em **FastAPI** que, no momento da autorização do pagamento, recebe os
dados da transação e devolve uma decisão de risco.

```text
POST /api/v1/score-transaction
→ validação (CPF 11, CNPJ 14, valores positivos, tipos)
→ carga do bundle HBOS do CPF (PostgreSQL + cache em memória)
→ cálculo de features (perfis salvos no bundle)
→ HBOS + regras de negócio (média ponderada)
→ hard-rule de viagem impossível
→ [se HBOS = deny → decisão final deny; XGBoost NÃO executa]
→ [se HBOS = approve ou challenge → XGBoost global]
→ consolidação dual
→ persistência de log completo
→ resposta: { "decision_final": "..." }
```

| Decisão | Significado de negócio |
|---|---|
| `approve` | Transação dentro do padrão — seguir fluxo normal |
| `challenge` | Caso questionável — merece atenção adicional |
| `deny` | Alto risco — negar/bloquear |

**Fundações já prontas:** decisão em camadas, log auditável, treino noturno + fila, cascata
dual, cache de modelos, testes automatizados, separação online/offline.

---

## 2. AS-IS: componentes de decisão

### 2.1 HBOS individual por CPF

- Não supervisionado, detecção de anomalia, **treinado por CPF**;
- Bundle serializado contém **modelo + scaler + perfis** (média do CPF, cartões,
  estabelecimentos, centróide geográfico);
- Servido com cache em memória para reduzir I/O no PostgreSQL;
- Histórico de treino de até ~730 dias;
- **Valor imediato mesmo com rótulo atrasado** — esta é a razão de existir do HBOS;
- Score alto = comportamento atípico. **Não é prova de fraude.**

### 2.2 XGBoost global

- Supervisionado, treinado com **fraude confirmada**;
- Atua como segunda linha estatística em cascata;
- **Não é ponto único de falha** (fail-safe da cascata);
- Cobre CPF novo e padrões de fraude em escala;
- Depende integralmente da qualidade e maturação dos rótulos.

### 2.3 Regras e hard rules

- Regras de valor, tempo, estabelecimento e geo;
- **Hard-rule de viagem impossível** — cenário clássico capturado com alta precisão;
- Hard rules críticas prevalecem sobre scores probabilísticos;
- Toda regra gera evidência e reason code auditável.

### 2.4 Cascata com short-circuit

`HBOS = deny` encerra a decisão sem executar o XGBoost. Isso protege latência, mas exige a
instrumentação descrita na seção 8.

---

## 3. AS-IS: divergências documentais abertas

### 3.1 Contrato da API

| Fonte | Saída |
|---|---|
| Especificação do microserviço | `score`, `decision`, `signals`, `features`, `feature_weights` |
| Implementação AS-IS | `{ "decision_final": "approve\|challenge\|deny" }` |

Limitação registrada na documentação: *"Resposta HTTP só com `decision_final` → integrador
não vê score/sinais. Detalhe está no log."*

**TO-BE — contrato versionado:**

```text
API v1: mantém decision_final; retrocompatível; não quebra integrações.
API v2: score, decision, signals, features, feature_weights, reason codes,
        model_versions — com autenticação, autorização por perfil,
        mascaramento e proteção contra exposição da lógica antifraude.
```

O orquestrador de `challenge` **não deve depender da resposta HTTP v1**: consome evento
interno, log estruturado, base de auditoria ou tópico de mensageria.

### 3.2 Número de features — item aberto

| Fonte | Quantidade |
|---|---|
| Apresentação AS-IS | 13 features + regras + hard-rule geográfica |
| PDF do microserviço | 10 features numéricas |

**Ação requerida:** auditoria do código de feature engineering para fixar a lista canônica,
versioná-la em contrato de features (schema registry) e alinhar a documentação. Enquanto não
houver conciliação, **não afirmar um número como definitivo**.

---

## 4. Orçamento de latência — restrição estruturante (p95 < 100 ms)

| Etapa | Budget p95 | Observação |
|---|---|---|
| Validação de payload | 5 ms | Pydantic |
| Carga do bundle (cache **hit**) | 8 ms | Memória |
| Cálculo de features | 25 ms | Maior consumidor — alvo de otimização |
| HBOS + regras + hard-rule | 12 ms | Determinístico |
| XGBoost global (quando executa) | 15 ms | Não executa se HBOS = deny |
| Consolidação dual | 5 ms | Média ponderada |
| Rede + serialização | 15 ms | — |
| Buffer de variação | 15 ms | Absorve picos |
| **Total** | **100 ms** | **Hard deadline** |
| Persistência de log/auditoria | **0 ms** | **Assíncrono, fire-and-forget** |

### Escada de degradação obrigatória

```text
Cache MISS do bundle HBOS:
→ tentar carregar do PostgreSQL com timeout de 20 ms
→ se exceder: decidir com XGBoost global + regras + hard rules
→ reason code: hbos_unavailable
→ disparar warm-up assíncrono do bundle
→ NUNCA estourar o deadline aguardando I/O de modelo

Falha do XGBoost:
→ manter decisão do HBOS + regras (fail-safe da cascata, já existente)
→ reason code: xgb_unavailable

Falha de dependência externa no fast path:
→ proibido no caminho síncrono; validadores externos vivem só no challenge
```

---

## 5. Lacuna prioritária: `challenge` sem ação operacional

### TO-BE

```text
ML + regras → challenge
→ evento fraud.challenge.created
→ fila de triagem
→ Agent Framework Workflows
→ validadores interligados
→ approve / deny / escalate
→ notificação sim/não
→ auditoria
```

### Contrato do evento (versionado e idempotente)

```json
{
  "event": "fraud.challenge.created",
  "schema_version": "1.0",
  "idempotency_key": "<transaction_id>:<schema_version>",
  "transaction_id": "…",
  "correlation_id": "…",
  "cpf_token": "<tokenizado, nunca em claro>",
  "occurred_at": "2026-08-13T11:36:00-03:00",
  "decision_initial": "challenge",
  "scores": { "hbos": 0.62, "xgb": 0.48, "final": 0.55 },
  "thresholds": { "approve_max": 0.40, "deny_min": 0.70 },
  "signals": ["valor_acima_padrao", "estabelecimento_novo"],
  "features": { "…": "…" },
  "feature_weights": { "…": "…" },
  "model_versions": { "hbos": "cpf/…/v12", "xgb": "global/v7" },
  "layers_executed": ["validacao","features","hbos","rules","xgb"],
  "short_circuit_layer": null,
  "ttl_seconds": 900
}
```

### SLOs do caminho de análise

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

---

## 6. Lacuna prioritária: invalidação de cache pós-treino

```text
Pipeline de treino
→ valida integridade do artefato e compatibilidade de schema de features
→ registra versão no model registry
→ publica bundle de forma atômica
→ promove versão
→ emite evento model.published
→ invalida cache distribuído (chave: cpf + model_version)
→ reload lazy (próxima requisição) ou eager (warm-up)
→ registra model_version_active por instância
→ dashboard confirma convergência entre réplicas
```

**Critérios de aceite:**

- 100% das publicações sem restart manual;
- Convergência de versão entre réplicas < 5 min;
- 100% das inferências com `model_version` registrada;
- Rollback para versão anterior < 10 min;
- Alerta automático de instância defasada.

---

## 7. Lacuna prioritária: política de cold start

```text
CPF novo + valor < R$ X + sem hard rule
  → approve com monitoramento reforçado

CPF novo + R$ X ≤ valor < R$ Y
  → challenge com step-up

CPF novo + valor ≥ R$ Y  ou  hard rule crítica
  → deny ou escalate

Em qualquer caso de CPF novo:
  → peso do HBOS = 0 (ou reduzido por baixa confiança)
  → peso do modelo global aumentado
  → reason code obrigatório: cold_start
```

---

## 8. Instrumentação do short-circuit e shadow

**Registrar por transação:** `layers_executed`, `layers_skipped`, `short_circuit_layer`,
`score_hbos`, `score_xgb`, `score_final`, regras acionadas, sinais, `feature_weights`,
`model_versions`, decisão final e `fallback_reason`.

**Amostragem shadow (1% a 5%):** avaliada assincronamente por todas as camadas, sem impactar
o tempo de resposta, mitigando viés de seleção no retreinamento.

---

## 9. AutoML: diretrizes

- **Permitido (offline):** exploração, comparação de modelos, feature importance (SHAP),
  challenger em shadow (≥ 4 semanas), rollout canário.
- **Vedado (online/hot path):** chamada remota síncrona ao Azure AutoML durante a
  autorização.
- **Configuração de referência:**
  - Classificação: `primary_metric: average_precision_score_weighted`, split temporal estrito.
  - Regressão: `primary_metric: normalized_root_mean_squared_error`, validação de calibração
    por faixas.
  - `blocked_models`: modelos que excedam o budget de inferência de 15 ms p95.

---

## 10. Agent Framework Workflows

- Restrito exclusivamente à esteira assíncrona de `challenge`.
- Validadores modulares com timeout, circuit breaker e fallback seguro.
- Agentes de IA atuam em triagem, enriquecimento e recomendação — nunca substituem hard
  rules em decisões críticas.

---

## 11. Qualidade de dados, validação temporal e rotulagem

- **Limiares de drift:** PSI < 0,10 (estável); 0,10–0,25 (alerta/revisão 7 dias); > 0,25
  (drift crítico/retreino); KS p-valor < 0,01.
- **Nulos em features críticas:** > 2% bloqueia promoção de modelo.
- **Divisão temporal obrigatória:** treino no passado, validação intermediária, teste no
  período mais recente.
- **Taxonomia de rótulos:** `fraude_confirmada`, `fraude_suspeita`, `em_disputa`,
  `legitima_confirmada`, `sem_desfecho` (nunca assumir `sem_desfecho` como legítima).

---

## 12. LGPD e governança

- Base legal documentada por finalidade (prevenção a fraudes / legítimo interesse).
- DPIA para decisões automatizadas de alto impacto.
- Reason codes mapeáveis para explicação ao titular.
- Tokenização de CPF em eventos, logs e filas.
- Retenção diferenciada entre logs de auditoria e payloads com dados brutos.

---

## 13. Viés e equidade

- Monitoramento segregado por coortes: tempo de relacionamento, canal, região, tipo de
  estabelecimento.
- Acompanhamento de FPR, FNR, recall, taxas de challenge e deny por segmento.
- Mitigação de viés de seleção decorrente de regras históricas e assimetria de massa de
  treino.

---

## 14. Critérios de aceite consolidados

1. Fast path mantém **p95 < 100 ms**, com orçamento por etapa monitorado.
2. **100%** dos `challenge` com desfecho rastreável.
3. **100%** das publicações de modelo aplicadas sem restart manual.
4. Política de cold start ativa, configurável e mensurada em coorte separada.
5. Dashboards de performance, drift, fallback, divergência HBOS/XGB e viés por coorte em
   operação.
6. AutoML permanece offline/shadow por **≥ 4 semanas** até demonstrar melhoria consistente.
7. Promoção apenas por champion/challenger com rollout canário e rollback definido (< 10 min).
8. Toda decisão explicável e auditável (score, sinais, features, pesos, camada decisora).
9. API v2 resolve a divergência de contrato, preservando a v1.
10. Validadores externos nunca degradam o SLA do caminho síncrono.
11. **Lista canônica de features conciliada** (10 × 13) e versionada em contrato.

---

## 15. Diretrizes obrigatórias para respostas futuras

1. Diferenciar sempre AS-IS, Lacuna/Risco, TO-BE e critério de aceite.
2. Não afirmar que AutoML, agentes ou orquestração estão em produção.
3. Não recomendar AutoML no hot path de autorização.
4. Tratar HBOS como detector de anomalia, não como prova de fraude.
5. Tratar XGBoost como supervisionado, dependente de rótulos maduros e validação temporal.
6. Priorizar `challenge`, invalidação de cache e cold start antes de expandir agentes de IA.
7. Preservar arquitetura em camadas, regras determinísticas, explicabilidade, auditabilidade
   e fallback.
8. Incluir LGPD, viés, validação temporal, rotulagem, drift e rollback em toda proposta de ML.
9. Considerar que a resposta HTTP atual pode expor apenas `decision_final`.
10. **Toda recomendação deve trazer número, limiar ou critério mensurável** — evitar
    formulações apenas descritivas.
11. Não afirmar quantidade de features como definitiva enquanto a divergência 10 × 13 não for
    conciliada.
