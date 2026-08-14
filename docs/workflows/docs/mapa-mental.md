# Mapa mental do projeto

Visão única do motor de score antifraude: o que existe, o que está quebrado, o que foi decidido e
em que ordem executar. Cada ramo aponta para o documento normativo correspondente.

## 1. Mapa geral

```mermaid
mindmap
  root((Motor de Score Antifraude))
    AS-IS
      Fluxo vigente
        Gate da Regra 83
        HBOS com approve terminal
        XGBoost decide o final
        Meta p95 abaixo de 100 ms
      Componentes
        HBOS individual por CPF
          Nao supervisionado
          Bundle em cache de memoria
          Janela de ate 730 dias
          Sinal comportamental
        XGBoost global
          Supervisionado
          Depende de rotulos maduros
        Regras e hard rules
          Deterministicas
          Reason code auditavel
      Contrato HTTP
        Expoe apenas decision_final
      Step-up existente
        WhatsApp no private label
        Acoplado a Regra 83
    Lacunas
      L1 Cobertura de ML presa ao gate
      L2 Approve terminal do HBOS
      L3 Challenge sem desfecho
      L4 Step-up acoplado e nao reutilizavel
      L5 Cache exige restart manual
      L6 Cold start indefinido
      L7 Short-circuit oculta camadas
      L8 API sem explicabilidade
      L9 Rotulos com maturacao tardia
    TO-BE
      ADR-0001 Topologia
        Busca unica de features
        Avaliacao paralela
        Short-circuit so em hard rule critica
        Camada de politica deterministica
        Regra 83 vira sinal
      ADR-0002 Papeis dos modelos
        HBOS nunca decide
        GBDT global champion
        LightGBM challenger
        Calibracao versionada
        Consolidacao deterministica
        Modelo dedicado de cold start
        Grafo pre-computado
      ADR-0003 Cold start
        Quatro faixas de historico
        Peso do HBOS por confianca
        Reason code cold_start
      ADR-0004 Publicacao de modelos
        Publicacao atomica
        Invalidacao granular por CPF
        Reconciliacao com o registry
        Rollback por configuracao
      Contratos
        Evento fraud.challenge.created
        API v1 preservada
        API v2 com explicabilidade
      Trilha de challenge
        Fila de triagem
        Validadores versionados
        Step-up desacoplado
        Escalate para humano
        Idempotencia por transacao
    Governanca
      LGPD
        CPF tokenizado
        Mascaramento no servidor
        Retencao com finalidade
        Direito a revisao
      Explicabilidade
        Reason codes inteligiveis
        Contribuicao por feature
      Vies e equidade
        Metricas por coorte
        Proxies controlados
        Sinais correlacionados limitados
      Auditoria
        Versoes por inferencia
        Evidencia por decisao
        Rastro por correlation_id
    MLOps
      Qualidade de dados
        Bloqueia o treino ao falhar
      Validacao temporal
        Split aleatorio proibido
      Maturacao de rotulos
        sem_desfecho nao e legitima
      Dados nao enviesados
        Shadow de 1 a 5 por cento
        Exploracao com teto de perda
      Drift
        PSI e KS por feature
        Divergencia entre modelos
      Promocao
        candidate
        challenger
        champion
        deprecated
        rolled_back
    Restricoes
      AutoML somente offline
      Nada de LLM no hot path
      Agentes nao substituem hard rules
      Nenhuma promocao por metrica isolada
      Fallback seguro nao e sempre deny
    Roadmap
      F0 Telemetria e shadow
      F1 Challenge operacional
      F2 Publicacao de modelos
      F3 API v2
      F4 Topologia paralela
      F5 Cold start
      F6 Calibracao e novos modelos
```

## 2. Como ler o mapa

O mapa tem uma direção de leitura: **AS-IS** descreve o que existe, **Lacunas** enumera o que
está quebrado, **TO-BE** traz a decisão registrada para cada lacuna, e **Roadmap** ordena a
execução. **Governança**, **MLOps** e **Restrições** são transversais — atravessam todas as fases
e não são etapas a cumprir e encerrar.

O ramo mais denso é o TO-BE porque é onde estão as decisões. O ramo mais importante é o de
**Restrições**: são os limites que não se negociam por conveniência de prazo.

## 3. Fluxo de decisão TO-BE

```mermaid
flowchart TD
    A[Transacao] --> B[Validacao de payload<br/>e autenticacao]
    B -->|invalido| B1[Rejeicao controlada<br/>reason code + evidencia]
    B --> C[Busca unica de features]
    C --> D{Hard rule critica?}
    D -->|sim| D1[Deny imediato<br/>unico short-circuit permitido]
    D -->|nao| E[Avaliacao paralela]

    E --> E1[HBOS do CPF<br/>score + contribuicoes]
    E --> E2[GBDT global<br/>ou modelo de cold start]
    E --> E3[Regras de negocio<br/>inclui Regra 83]
    E --> E4[Sinais de grafo<br/>pre-computados]

    E1 --> F[Calibracao<br/>artefato versionado]
    E2 --> F
    E3 --> F
    E4 --> F

    F --> G[Camada de politica<br/>thresholds por valor, canal,<br/>produto e coorte]
    G -->|baixo risco| H1[Approve]
    G -->|risco intermediario| H2[Challenge]
    G -->|alto risco| H3[Deny]

    H1 --> I[Evento interno assincrono<br/>score, sinais, features,<br/>pesos e versoes]
    H2 --> I
    H3 --> I
    D1 --> I
    H2 --> J[Trilha de challenge]

    style D1 fill:#ffd9d9,stroke:#c23b3b
    style H1 fill:#d9f2d9,stroke:#3b8c3b
    style H2 fill:#ffe9cc,stroke:#c98b2e
    style H3 fill:#ffd9d9,stroke:#c23b3b
```

O ponto que diferencia este desenho do AS-IS: nenhuma camada emite decisão terminal, exceto hard
rule crítica. Todas as camadas contribuem sinal, e a decisão nasce num só lugar.

## 4. Trilha de challenge

```mermaid
flowchart TD
    A[Challenge] --> B[Evento<br/>fraud.challenge.created]
    B --> C[Persistencia de contexto<br/>e evidencias]
    C --> D[Fila de triagem]
    D --> E[Workflow de validadores]

    E --> V1[Regras adicionais]
    V1 -->|deny alta confianca| Z2
    V1 --> V2[Blocklist e bureau]
    V2 -->|deny alta confianca| Z2
    V2 --> V3[Geolocalizacao e dispositivo]
    V3 --> V4[Historico estendido]
    V4 --> V5[Step-up de autenticacao<br/>inclui WhatsApp]

    V5 -->|cliente confirma| Z1
    V5 -->|cliente nega| Z2
    V5 -->|nao responde ate timeout| Z3

    V4 --> F[Consolidacao]
    F --> Z1[Approve]
    F --> Z2[Deny]
    F --> Z3[Escalate]

    Z3 --> H[Fila de analise humana]
    H --> Z1
    H --> Z2

    Z1 --> N[Notificacao idempotente]
    Z2 --> N
    N --> AUD[Auditoria]

    style Z1 fill:#d9f2d9,stroke:#3b8c3b
    style Z2 fill:#ffd9d9,stroke:#c23b3b
    style Z3 fill:#ffe9cc,stroke:#c98b2e
```

Detalhe que corrige o comportamento atual: **não responder ao step-up leva a `escalate`, não a
`deny`**. Silêncio do cliente é ausência de informação, não fraude confirmada — e essa distinção
precisa sobreviver até a base de rótulos.

## 5. Dependência entre as fases

```mermaid
flowchart LR
    F0[F0 Telemetria e shadow]
    F1[F1 Challenge operacional]
    F2[F2 Publicacao de modelos]
    F3[F3 API v2]
    F4[F4 Topologia paralela]
    F5[F5 Cold start]
    F6[F6 Calibracao e novos modelos]

    F0 --> F1
    F0 --> F2
    F0 --> F3
    F1 --> F4
    F2 --> F4
    F4 --> F5
    F1 --> F5
    F2 --> F6
    F0 --> F6

    style F0 fill:#dfe9ff,stroke:#3b5bc9
    style F1 fill:#dfe9ff,stroke:#3b5bc9
```

As duas fases destacadas são as que destravam todo o resto. A aresta `F1 → F4` é a mais fácil de
ignorar e a mais custosa de errar: a topologia paralela **aumenta o volume de challenge**, porque
passa a dar escore a tráfego antes aprovado direto. Sem fila de triagem operando, isso gera
volume sem desfecho — pior que o AS-IS.

## 6. Índice cruzado: lacuna, decisão e fase

| Lacuna | Decisão registrada | Fase |
|---|---|---|
| L1 Cobertura de ML presa ao gate | [ADR-0001](adr/0001-topologia-de-decisao.md) | F4 |
| L2 Approve terminal do HBOS | [ADR-0002](adr/0002-papeis-dos-modelos.md) | F4 |
| L3 Challenge sem desfecho | [Trilha de challenge](workflows/trilha-de-challenge.md) | F1 |
| L4 Step-up acoplado e não reutilizável | [Trilha de challenge](workflows/trilha-de-challenge.md) | F1 |
| L5 Cache exige restart manual | [ADR-0004](adr/0004-publicacao-de-modelos-e-cache.md) | F2 |
| L6 Cold start indefinido | [ADR-0003](adr/0003-politica-de-cold-start.md) | F5 |
| L7 Short-circuit oculta camadas | [Telemetria](observabilidade/telemetria-de-decisao.md) | F0 |
| L8 API sem explicabilidade | [API versionada](contratos/api-versionada.md) | F3 |
| L9 Rótulos com maturação tardia | [MLOps](mlops/dados-rotulos-e-promocao.md) | F6 |

Detalhamento das lacunas em [contexto AS-IS](arquitetura/00-contexto-as-is.md); ordenação completa
e riscos transversais em [roadmap](roadmap.md).
