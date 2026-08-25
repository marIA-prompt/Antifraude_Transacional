# Mapa mental do projeto

Visão única: o que existe no microserviço FastAPI, o que está aberto, o que foi decidido e
em que ordem executar. Briefing fonte: [contexto-operacional.md](contexto-operacional.md).

## 1. Mapa geral

```mermaid
mindmap
  root((Motor de Score FastAPI))
    AS-IS
      POST /api/v1/score-transaction
      Cascata
        HBOS deny encerra
        XGBoost se approve ou challenge
        Hard-rule viagem impossivel
        Consolidacao dual
      Componentes
        HBOS por CPF
          Anomalia nao fraude
          Bundle cache + PostgreSQL
          Ate 730 dias
        XGBoost global
          Fraude confirmada
          Fail-safe da cascata
        Regras e hard rules
      HTTP
        So decision_final
      Fundacoes
        Log auditavel
        Treino noturno
        Testes
        Online vs offline
    Divergencias abertas
      D-1 API 5 campos vs decision_final
      D-2 Features 10 vs 13
      D-3 NEG83 / Motor H vs este score
      D-4 Ordem da cascata no repo antigo
    Lacunas
      L1 Challenge sem desfecho
      L2 Cache sem invalidacao
      L3 Cold start indefinido
      L4 Short-circuit cego
      L5 API sem explicabilidade
      L6 Features nao canonicas
      L7 Rotulos imaturos
      L8 Relacao NEG83 aberta
      L9 Log no caminho sincrono
    TO-BE
      ADR-0001 Cascata + degradacao
        Timeout bundle 20 ms
        hbos_unavailable
        xgb_unavailable
        Sem dependencia externa no fast path
      ADR-0002 Papeis
        HBOS anomalia
        XGBoost supervisado
        AutoML so offline
        Motor H fora do hot path
      ADR-0003 Cold start
        Faixas X e Y
        Peso HBOS zero
        Reason code cold_start
      ADR-0004 Publicacao
        Sem restart
        Convergencia menor que 5 min
        Rollback menor que 10 min
      Contratos
        Evento fraud.challenge.created
        API v1 congelada
        API v2 autorizada
        Registry de features candidate
          10 nomes PDF
          13 nomes apresentacao
          canonical_list nula
      Trilha de challenge
        Fila
        Validadores 800 ms / 2 s
        Escalate 24 h igual a 0
    Fora deste motor
      Motor H
        Ranking LATER_SUCCESS
        33 features FIRST_NEG83
        Policies H-05 H-10 H-15
        Teste assistido
      MAPA
        Diagnostico antes de modelo novo
        Escassez de rotulos
    Governanca
      LGPD
        cpf_token
        DPIA
        Retencao diferenciada
      Drift
        PSI 0.10 / 0.25
        Nulos criticos 2 por cento
      Vies
        FPR FNR por coorte
    Restricoes
      p95 menor que 100 ms
      AutoML vedado no hot path
      Agentes so na trilha challenge
      Nao afirmar 10 ou 13 features
      Score skipped e null
      sem_desfecho nao e negativa
    Roadmap
      F0 Telemetria shadow D-2 D-3
      F1 Challenge
      F2 Publicacao de modelos
      F3 API v2
      F4 Cold start
      F5 Calibracao AutoML offline
```

## 2. Fluxo AS-IS do microserviço

```mermaid
flowchart TD
    A[POST /api/v1/score-transaction] --> B[Validacao Pydantic]
    B -->|invalido| B1[Erro controlado]
    B --> C[Bundle HBOS cache / PostgreSQL]
    C --> D[Calculo de features]
    D --> E[HBOS + regras]
    E --> F[Hard-rule viagem impossivel]
    F -->|veto| ZD[deny]
    F --> G{HBOS = deny?}
    G -->|sim| ZD
    G -->|approve ou challenge| H[XGBoost global]
    H --> I[Consolidacao dual]
    I -->|baixo| ZA[approve]
    I -->|intermediario| ZC[challenge]
    I -->|alto| ZD
    ZA --> L[Log]
    ZC --> L
    ZD --> L
    ZC -.->|TO-BE| EV[fraud.challenge.created]

    style ZD fill:#ffd9d9,stroke:#c23b3b
    style ZA fill:#d9f2d9,stroke:#3b8c3b
    style ZC fill:#ffe9cc,stroke:#c98b2e
```

O ponto que diferencia este desenho de propostas anteriores: **o deny do HBOS é terminal no
AS-IS**. Instrumentar e amostrar em shadow é a mitigação imediata; mudar a topologia exige
números ([ADR-0001](adr/0001-topologia-de-decisao.md)).

## 3. Trilha de challenge (TO-BE)

```mermaid
flowchart TD
    A[Challenge] --> B[Evento fraud.challenge.created]
    B --> C[Fila de triagem]
    C --> E[Workflow de validadores]
    E --> V1[Regras adicionais]
    V1 -->|deny alta confianca| Z2
    V1 --> V2[Blocklist e bureau]
    V2 -->|deny alta confianca| Z2
    V2 --> V3[Geo / device / historico]
    V3 --> V5[Step-up]
    V5 -->|confirma| Z1
    V5 -->|nega| Z2
    V5 -->|nao responde| Z3
    V3 --> F[Consolidacao]
    F --> Z1[Approve]
    F --> Z2[Deny]
    F --> Z3[Escalate]
    Z3 --> H[Fila humana]
    Z1 --> N[Notificacao idempotente]
    Z2 --> N
    H --> N

    style Z1 fill:#d9f2d9,stroke:#3b8c3b
    style Z2 fill:#ffd9d9,stroke:#c23b3b
    style Z3 fill:#ffe9cc,stroke:#c98b2e
```

Não-resposta ao step-up → `escalate`, não `deny`.

## 4. Dependência entre fases

```mermaid
flowchart LR
    F0[F0 Telemetria shadow D-2 D-3]
    F1[F1 Challenge]
    F2[F2 Publicacao]
    F3[F3 API v2]
    F4[F4 Cold start]
    F5[F5 Calibracao AutoML offline]

    F0 --> F1
    F0 --> F2
    F0 --> F3
    F1 --> F4
    F2 --> F4
    F2 --> F5
    F0 --> F5

    style F0 fill:#dfe9ff,stroke:#3b5bc9
    style F1 fill:#dfe9ff,stroke:#3b5bc9
```

## 5. Índice cruzado

| Item | Documento | Fase |
|---|---|---|
| AS-IS do FastAPI | [contexto AS-IS](arquitetura/00-contexto-as-is.md) | — |
| D-1 a D-4 | [divergências](arquitetura/divergencias-documentais.md) | F0 |
| p95 100 ms | [orçamento](arquitetura/orcamento-de-latencia.md) | todas |
| Cascata + degradação | [ADR-0001](adr/0001-topologia-de-decisao.md) | F0 |
| Papéis HBOS/XGB/AutoML | [ADR-0002](adr/0002-papeis-dos-modelos.md) | F5 |
| Cold start | [ADR-0003](adr/0003-politica-de-cold-start.md) | F4 |
| Cache / registry | [ADR-0004](adr/0004-publicacao-de-modelos-e-cache.md) | F2 |
| Challenge | [trilha](workflows/trilha-de-challenge.md) | F1 |
| Features 10 × 13 | [features](contratos/features.md) | F0 |
| MAPA | [acompanhamento](mlops/acompanhamento-modelagem.md) | paralelo |
| Motor H / NEG83 | [Motor H](recuperacao/motor-h-neg83.md) | fora do hot path |
| LGPD | [governança](governanca/lgpd-e-dados-sensiveis.md) | transversal |
