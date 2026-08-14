# Diagramas TO-BE

Os diagramas abaixo consolidam o texto operacional e os três fluxogramas de
referência, já **reconciliados** (Regra 83 como hard rule; WhatsApp na trilha
de challenge; AutoML/agentes fora do hot path).

## 1. Hot path síncrono (AS-IS evoluído)

```mermaid
flowchart TD
  A[Receber transação + correlation_id] --> B{Payload válido?}
  B -->|Não| R[Rejeitar / erro controlado]
  B -->|Sim| C[Calcular features]
  C --> D[Hard rules incl. Regra 83]
  D --> E{Hard rule crítica?}
  E -->|Sim| DENY1[Deny imediato + reason code]
  E -->|Não| F[Política de cold start]
  F --> G{Política encerra?}
  G -->|Sim| DEC[Approve / Challenge / Deny]
  G -->|Não| H[HBOS individual — sinal]
  H --> I[XGBoost global — score]
  I --> J{Faixa consolidada}
  J -->|Low| APP[Approve]
  J -->|High| DENY2[Deny]
  J -->|Medium| CH[Challenge]
  CH --> EV[Outbox: fraud.challenge.created]
```

SLA: p95 < 100 ms até `Approve` / `Deny` / `Challenge` (a publicação do outbox
é local e assíncrona em relação a integrações externas).

## 2. Trilha operacional de challenge (TO-BE planejada)

```mermaid
flowchart TD
  EV[fraud.challenge.created] --> P[Persistir contexto + fila]
  P --> W[Workflow de validadores]
  W --> V1[Regras adicionais]
  V1 --> V2[Blocklist / Bureau]
  V2 --> V3[Geo / Device]
  V3 --> V4[Histórico estendido]
  V4 --> C{Resultado consolidado}
  C -->|Approve| A[Approve pós-challenge]
  C -->|Deny| D[Deny pós-challenge]
  C -->|Escalate| H[Fila humana / step-up WhatsApp]
  A --> N[Notificação + auditoria]
  D --> N
  H --> N
```

Agent Framework Workflows entra **nesta** trilha, não no hot path. Ainda não
está em produção.

## 3. Relação com o fluxo de compra private label

```mermaid
flowchart TD
  CARD[Cartão private label] --> TX[Transação de compra]
  TX --> AUTH{Autenticador}
  AUTH -->|Não autenticado| NEG[Compra negada]
  AUTH -->|Autenticado| MOTOR[Motor antifraude hot path]
  MOTOR -->|approve| OK[Compra aprovada]
  MOTOR -->|deny| NEG
  MOTOR -->|challenge| ST[Step-up / fila — ex. WhatsApp]
  ST -->|Confirmado / approve| OK
  ST -->|Não confirmado / deny| NEG
  ST -->|escalate| HUM[Análise humana]
  HUM --> OK
  HUM --> NEG
```

## 4. Ciclo de modelos (offline)

```mermaid
flowchart LR
  D[Dados + rótulos maduros] --> Q[Qualidade e leakage]
  Q --> T[Treino HBOS / XGBoost / AutoML offline]
  T --> V[Validação temporal]
  V --> REG[Registry candidate]
  REG --> SH[Shadow]
  SH --> CAN[Canário]
  CAN --> CH[Champion]
  CH --> PUB[model.published]
  PUB --> CACHE[Reload de cache]
  CAN -->|regressão| RB[Rollback]
```

## 5. Cascata AS-IS técnica (documentada, não alvo)

Mantida para rastreabilidade da divergência:

```mermaid
flowchart TD
  T[Transação] --> R{Caiu na Regra 83?}
  R -->|Não| A1[Aprovado]
  R -->|Sim| H[Motor HBOS]
  H -->|Aprovado| A2[Aprovado]
  H -->|Reprovado| X[XGBoost]
  H -->|Challenge| X
  X --> A3[Aprovado]
  X --> D[Reprovado]
  X --> C[Challenge]
```

Essa cascata **não** é o TO-BE. Ver [ADR-006](adr/006-regra-83-hard-rule.md).
