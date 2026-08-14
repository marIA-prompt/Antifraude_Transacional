# Roadmap de execução

As fases estão ordenadas por **dependência técnica**, não por esforço. Deliberadamente sem
estimativa de calendário: o que importa aqui é o que precisa existir antes de cada passo.

A regra que organiza tudo: **instrumentar antes de mudar decisão, e operacionalizar desfecho antes
de gerar mais casos.** Endurecer a política antes de existir fila de triagem produz volume sem
desfecho, que é pior do que o AS-IS.

## Fase 0 — Telemetria e shadow

**Por que primeiro:** é o que torna todas as outras fases mensuráveis, e é a fase mais barata em
relação ao valor. Sem ela, nenhuma mudança posterior pode ser avaliada, e nenhuma promoção de
modelo é defensável.

Escopo: registro por transação de camadas executadas, camada que encerrou, camada que elevou o
risco, escores, pesos, versões e fallback; amostra de shadow de 1% a 5% cobrindo tráfego **dentro
e fora** do gate da Regra 83; dashboards de latência, decisão, cobertura de camada e fallback.

Referência: [telemetria de decisão](observabilidade/telemetria-de-decisao.md).

**Saída que destrava o resto:** a resposta às perguntas abertas 1 e 2 do
[contexto AS-IS](arquitetura/00-contexto-as-is.md) — volume e taxa de fraude do tráfego fora do
gate, e o threshold efetivo do approve terminal do HBOS.

## Fase 1 — Operacionalizar o `challenge`

**Depende de:** Fase 0 (para medir o efeito).

Sequência interna, na ordem em que deve ser implementada:

1. publicação do evento `fraud.challenge.created` para transações em banda de challenge;
2. persistência de contexto e evidências da decisão inicial;
3. fila de triagem;
4. regras adicionais e calibração de decisão;
5. step-up de autenticação, quando aplicável — absorvendo o WhatsApp como validador desacoplado
   da Regra 83 e do private label;
6. fila de análise humana para resultado `escalate`;
7. notificação idempotente e rastreável;
8. integrações externas: bureau, blocklist, geolocalização, device intelligence;
9. agentes de IA assíncronos como apoio à triagem — **somente após** os controles determinísticos.

Referências: [contrato do evento](contratos/evento-challenge.md),
[trilha de challenge](workflows/trilha-de-challenge.md).

**Critério de saída:** 100% dos casos `challenge` com desfecho rastreável e idempotência
comprovada por teste de reentrega.

## Fase 2 — Publicação de modelos e invalidação de cache

**Depende de:** Fase 0 (versões registradas por inferência).

**Por que antes de qualquer modelo novo:** sem publicação atômica, invalidação de cache e rollback
por configuração, cada promoção volta a exigir restart manual, e o rollback chega tarde justamente
quando o tempo importa.

Referência: [ADR-0004](adr/0004-publicacao-de-modelos-e-cache.md).

**Critério de saída:** publicação sem restart manual, dashboard de convergência da frota e
rollback exercitado com tempo medido.

## Fase 3 — API v2 com explicabilidade

**Depende de:** Fase 0 (os dados a expor precisam existir de forma estruturada).

Pode correr em paralelo às fases 1 e 2, porque não altera decisão. Requer autenticação,
autorização por perfil, mascaramento e rate limiting específico.

Referência: [API versionada](contratos/api-versionada.md).

**Critério de saída:** v1 byte-compatível com o AS-IS e nenhum consumidor da v1 alterado.

## Fase 4 — Topologia paralela e camada de política

**Depende de:** Fases 0, 1 e 2. Fase 1 é pré-requisito rígido, porque esta fase **aumenta o
volume de challenge** ao dar escore a tráfego que antes era aprovado direto.

Escopo: busca única de features, avaliação paralela das camadas, short-circuit restrito a hard
rules críticas, camada de política determinística com thresholds configuráveis, Regra 83 rebaixada
de gate a sinal.

Rollout: shadow puro → medição de impacto de atrito → calibração de thresholds contra a capacidade
da fila → canário → promoção, com rollback por configuração.

Referências: [ADR-0001](adr/0001-topologia-de-decisao.md),
[ADR-0002](adr/0002-papeis-dos-modelos.md).

**Critério de saída:** nenhuma transação decidida sem escore (exceto hard rule documentada) e p95
abaixo de 100 ms com todas as camadas ativas.

## Fase 5 — Política de cold start

**Depende de:** Fase 4 (o modelo dedicado precisa da topologia com pesos configuráveis) e Fase 1
(o challenge de CPF novo precisa ter desfecho).

Escopo: faixas de histórico, peso do HBOS proporcional à confiança, modelo dedicado de cold start
com calibração própria, decisão modulada por valor/canal/produto/hard rule, reason code
`cold_start`.

Referência: [ADR-0003](adr/0003-politica-de-cold-start.md).

**Critério de saída:** métricas por faixa de histórico e thresholds ajustáveis sem redeploy.

## Fase 6 — Calibração explícita e novos modelos

**Depende de:** Fase 2 (registry e publicação) e Fase 0 (base de avaliação não enviesada).

**Por que último:** antes disso não existe base de avaliação confiável para promover nada. Um
ganho estatístico medido sobre dados filtrados pela política atual não se sustenta em produção.

Escopo: calibração isotônica/Platt como artefato versionado; LightGBM como challenger do XGBoost;
features de grafo pré-computadas; modelos de sequência e detecção de anomalia global apenas em
shadow ou como validadores assíncronos; AutoML offline apoiando a esteira champion/challenger.

Referências: [ADR-0002](adr/0002-papeis-dos-modelos.md),
[MLOps](mlops/dados-rotulos-e-promocao.md).

**Critério de saída:** promoção de modelo com o conjunto completo de métricas, incluindo coortes,
calibração e latência.

## Resumo de dependências

Versão em diagrama no [mapa mental](mapa-mental.md#5-dependência-entre-as-fases).

```text
Fase 0 (telemetria + shadow)
  ├── Fase 1 (challenge operacional)
  │     └── Fase 4 (topologia paralela + política)
  │           └── Fase 5 (cold start)
  ├── Fase 2 (publicação de modelos)
  │     ├── Fase 4
  │     └── Fase 6 (calibração + novos modelos)
  └── Fase 3 (API v2)  [independente das demais]
```

## Riscos transversais

| Risco | Mitigação |
|---|---|
| Fase 4 aumenta atrito e volume de fila abruptamente | Shadow puro e calibração de thresholds contra capacidade operacional antes de qualquer efeito na decisão |
| Rótulos imaturos inflam métricas de fases 5 e 6 | Janela de maturação aplicada ao corte de treino; `sem_desfecho` nunca como negativa |
| Custo de CPU por transação cresce na Fase 4 | Medição em carga de pico antes do rollout; o custo é de CPU, não de I/O |
| Agentes de IA antecipados antes dos controles determinísticos | Ordenados explicitamente como item 9 da Fase 1 |
| Perda de evento de publicação de modelo deixa instância defasada | Reconciliação periódica contra o registry, independente do evento |
