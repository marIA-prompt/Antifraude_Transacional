# ADR-0003 — Política de cold start

- **Status:** proposto
- **Depende de:** [ADR-0001](0001-topologia-de-decisao.md), [ADR-0002](0002-papeis-dos-modelos.md)
- **Lacuna endereçada:** L6 (cold start indefinido no fluxo vigente)

## Contexto

### AS-IS

Um CPF novo não possui bundle HBOS, porque o modelo individual é treinado sobre histórico do
próprio cliente. No fluxo vigente, com a Regra 83 como gate e o HBOS como primeira camada de
modelo, o caminho de uma transação de CPF sem histórico **não está documentado**: não se sabe
se ela vai direto ao XGBoost, se recebe aprovação padrão ou se depende de comportamento
implícito do carregador de bundles.

### Lacuna/Risco

A aprovação padrão de CPF novo reduz atrito na entrada do cliente, mas concentra exposição a
fraude exatamente onde não há sinal comportamental. Ao mesmo tempo, endurecer indiscriminadamente
o tratamento de CPF novo penaliza clientes legítimos em aquisição — é a coorte com maior risco
de viés do sistema, e a que mais afeta a experiência de primeiro uso.

Há ainda um risco silencioso de calibração: alimentar o modelo global com features de histórico
ausentes ou imputadas produz escores mal calibrados, porque o modelo aprendeu a confiar nessas
features. O resultado é uma decisão aparentemente probabilística sobre um escore que não
corresponde à probabilidade real de fraude naquela coorte.

## Decisão

**1. Cold start é uma condição medida, não binária.** A elegibilidade ao HBOS depende de
critérios explícitos e configuráveis, não da mera existência do bundle:

```text
sem_historico     : nenhuma transação observada
historico_minimo  : abaixo do número mínimo de transações ou de dias configurado
historico_parcial : atende ao mínimo, mas abaixo do volume de confiança plena
historico_pleno   : elegível a peso integral do HBOS
```

Os limites de cada faixa são configuração versionada, não constantes de código.

**2. Peso do HBOS proporcional à confiança do histórico.** Peso nulo em `sem_historico` e
`historico_minimo`; peso reduzido em `historico_parcial`; peso integral em `historico_pleno`.

**3. Modelo dedicado de cold start.** Nas faixas sem histórico suficiente, o escore de risco
vem do GBDT treinado sem features derivadas do histórico do CPF (ADR-0002), com **calibração
própria** ajustada na mesma coorte.

**4. Decisão modulada por exposição, não por regra única.** A política combina faixa de
histórico, valor, canal, produto, tipo de transação e hard rules:

```text
CPF novo + baixo valor + sem hard rule
→ approve com monitoramento reforçado

CPF novo + valor intermediário
→ challenge com step-up de autenticação

CPF novo + alto valor  ou  hard rule crítica
→ deny ou escalate
```

**5. Reason code obrigatório.** Toda decisão influenciada pela política registra
`cold_start` e a faixa de histórico aplicada, de forma que a coorte seja reconstituível em
análise posterior sem inferência indireta.

**6. Thresholds configuráveis sem redeploy**, com trilha de auditoria de alteração.

## Consequências

- Existe um caminho definido e testável para CPF novo, eliminando comportamento implícito do
  carregador de bundles.
- A coorte de cold start passa a ser mensurável de ponta a ponta, o que é pré-requisito para as
  avaliações de viés e equidade descritas em
  [MLOps](../mlops/dados-rotulos-e-promocao.md).
- Custo: mais um modelo e mais uma calibração para versionar, monitorar e promover.
- O aumento de `challenge` na coorte de CPF novo pressiona a fila de triagem. A política só deve
  endurecer depois que a [trilha de challenge](../workflows/trilha-de-challenge.md) estiver
  operacional — caso contrário, cria-se volume sem desfecho, que é pior do que o AS-IS.

## Critérios de aceite

- Métricas separadas para CPF novo e CPF com histórico, quebradas pelas quatro faixas de
  histórico.
- Por coorte: taxa de fraude confirmada, taxa de challenge, taxa de deny, taxa de aprovação
  legítima e taxa de reversão após step-up ou análise humana.
- Thresholds e limites de faixa alteráveis sem redeploy, versionados e auditáveis.
- Reason code `cold_start` presente em 100% das decisões em que a política foi aplicada.
- Peso efetivo do HBOS registrado por transação, comprovando que é nulo nas faixas sem
  histórico suficiente.
- Calibração do modelo de cold start avaliada na própria coorte, não na população geral.
- Revisão periódica documentada do impacto em atrito, receita e perda por fraude, com decisão
  registrada de manter ou ajustar os thresholds.
