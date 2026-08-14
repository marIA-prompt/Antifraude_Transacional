# ADR-0004 — Publicação de modelos e invalidação de cache

- **Status:** proposto
- **Lacuna endereçada:** L5 (cache exige restart ou limpeza manual após retreino)

## Contexto

### AS-IS

Bundles de HBOS (modelo, scaler, perfis estatísticos, metadados) e o modelo global são servidos
a partir de cache em memória, o que é a razão da latência baixa e não deve mudar.

### Lacuna/Risco

Depois de um retreinamento, o serviço pode continuar usando versões antigas em cache, exigindo
restart ou limpeza manual. Isso produz três problemas de gravidade crescente:

1. **Defasagem silenciosa** — instâncias diferentes decidem com versões diferentes, sem que
   ninguém saiba. A mesma transação teria decisões distintas dependendo do pod que a atendeu.
2. **Análise post-mortem inválida** — sem a versão registrada por inferência, não é possível
   atribuir um resultado ruim a um modelo específico.
3. **Rollback lento** — reverter uma promoção ruim depende de intervenção manual, justamente
   no momento em que o tempo importa.

## Decisão

### Pipeline de publicação

```text
Pipeline de treino
→ valida artefato (integridade, assinatura, tamanho, carregabilidade)
→ valida compatibilidade de schema de features
→ valida presença da calibração correspondente
→ registra versão no model registry
→ publica bundle de modo atômico
→ promove a versão
→ emite evento model.published
→ invalida cache distribuído
→ reload lazy ou eager por instância
→ registra model_version_active por instância
→ dashboard confirma convergência da frota
```

**Publicação atômica** significa escrita em caminho novo e imutável seguida de troca de ponteiro
de versão. Nenhuma instância deve conseguir observar um bundle parcialmente escrito.

**Invalidação em duas camadas.** O evento `model.published` invalida a chave no cache distribuído
e sinaliza as instâncias para recarregar o cache local. Enquanto a nova versão não estiver
carregada e validada, a instância continua servindo a anterior — degradar para "sem modelo"
nunca é aceitável no fast path.

### Estados no model registry

```text
candidate    → artefato registrado, ainda não exposto a tráfego
challenger   → avaliado em shadow contra o champion
champion     → serve as decisões de produção
deprecated   → substituído, mantido para auditoria e reprodutibilidade
rolled_back  → promovido e revertido; motivo do rollback registrado
```

### Especificidade dos bundles por CPF

O HBOS tem uma característica que o diferencia do modelo global: são muitos artefatos pequenos,
retreinados em cadência própria por CPF. Invalidação global a cada retreino individual
provocaria tempestade de recarga. Decisão: **invalidação granular por chave de CPF**, com o
evento `model.published` do HBOS carregando o conjunto de identificadores afetados, e a versão
do bundle registrada por inferência da mesma forma que a do modelo global.

### Rollback

Rollback é troca de ponteiro de versão, acionável por configuração, sem deploy e sem
reprocessamento. O estado `rolled_back` bloqueia repromoção acidental da mesma versão sem
revisão explícita.

## Consequências

- Publicações passam a ser observáveis e reversíveis; a frota tem convergência verificável.
- Toda inferência carrega a identidade completa dos artefatos usados, o que torna possível
  atribuir performance e fraude a versões específicas.
- Custo: infraestrutura de mensageria e cache distribuído entra no caminho de publicação, com
  necessidade de tratamento de evento perdido — daí a exigência de reconciliação periódica
  (a instância compara sua versão ativa com a versão promovida no registry, independentemente
  do evento).
- A validação de schema de features cria acoplamento explícito entre pipeline de treino e
  serviço de autorização. Isso é intencional: é o ponto onde uma incompatibilidade deve falhar,
  em vez de produzir escore silenciosamente errado.

## Critérios de aceite

- 100% das publicações de modelo aplicadas sem restart manual.
- Toda inferência registra a versão de modelo e de calibração usadas, inclusive a versão do
  bundle HBOS do CPF avaliado.
- Instâncias com defasagem acima do limite configurado são identificadas e alertadas, com
  dashboard de convergência da frota.
- Rollback para a versão anterior executável por configuração, com tempo medido e registrado em
  exercício de teste.
- Publicação falha, sem promover, quando a integridade do artefato, a compatibilidade de schema
  de features ou a presença da calibração não são satisfeitas.
- Reconciliação periódica detecta divergência entre versão ativa na instância e versão promovida
  no registry, mesmo com perda do evento `model.published`.
- Nenhuma instância serve decisão sem modelo carregado; falha de carga mantém a versão anterior
  e emite alerta.
