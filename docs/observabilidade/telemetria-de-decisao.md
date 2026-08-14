# Telemetria de decisão, short-circuit e shadow

## Contexto

### AS-IS

O fluxo vigente encerra a análise antecipadamente em dois pontos: quando a Regra 83 não é
acionada (aprovação direta) e quando o HBOS aprova (o modelo global não roda).

### Lacuna/Risco

O short-circuit protege a latência, mas produz cegueira operacional:

- não se sabe como as camadas posteriores teriam se comportado nos casos encerrados antes;
- os dados de retreinamento herdam o viés das camadas que filtraram o tráfego;
- na análise de um incidente, não é possível reconstituir qual camada elevou o risco e qual o
  encerrou;
- uma degradação de camada posterior pode passar despercebida por muito tempo, porque ela quase
  nunca é exercitada.

## TO-BE: registro obrigatório por transação

Para **toda** transação, independentemente da decisão:

```text
camadas executadas
camadas não executadas
camada que encerrou a decisão
camada que elevou o risco
score HBOS
peso efetivo aplicado ao HBOS
score do modelo global
score do modelo de cold start
score consolidado calibrado
regras acionadas
sinais
versões dos modelos, da calibração, das regras e da política
coorte de histórico
decisão final
motivo do fallback, quando aplicável
latência por camada
```

Duas observações que evitam erro de interpretação depois:

- **`camada_que_encerrou` e `camada_que_elevou_o_risco` são campos distintos.** Confundi-los
  distorce a análise de causa: a política pode encerrar como `deny` um risco que foi elevado por
  uma regra de negócio três camadas antes.
- **Peso efetivo do HBOS é obrigatório.** Sem ele não se distingue "HBOS não acusou anomalia" de
  "HBOS foi zerado por cold start".

O registro é assíncrono e fora do caminho síncrono da resposta, para não consumir orçamento de
latência.

## TO-BE: avaliação em shadow

```text
Amostra configurável de 1% a 5% das transações
→ avaliada em shadow por todas as camadas
→ não interfere na decisão online
→ usada para medir divergência, desempenho, calibração e viés
```

Requisito que costuma ser esquecido: a amostra precisa cobrir **o tráfego que não aciona a Regra
83**. Amostrar apenas dentro do gate reproduz exatamente o viés que o shadow existe para medir.
A amostragem deve ser aleatória e reprodutível (semente derivada do `transaction_id`), para que a
mesma transação caia consistentemente dentro ou fora da amostra em reprocessamentos.

Avaliações de shadow são publicadas no mesmo contrato de evento com
`execution.shadow_mode = true`, e consumidores operacionais devem filtrar por esse campo para não
contaminar a fila de triagem.

## Métricas e alertas

**Latência.** p50, p95 e p99 do fast path, por camada e no total. Alerta ao aproximar-se da meta
de 100 ms no p95.

**Decisão.** Distribuição de approve, challenge e deny; taxa de challenge; taxa de aprovação
legítima; distribuição de escore consolidado.

**Cobertura de camada.** Percentual de transações em que cada camada foi executada. Queda abrupta
indica falha silenciosa de dependência ou short-circuit indevido.

**Modelos.** `model_version_active` por instância, convergência da frota após publicação,
divergência entre HBOS, modelo global e challenger, deriva de calibração.

**Fallback.** Taxa de fallback por camada e motivo. Fallback silencioso é o modo de falha mais
perigoso do sistema, porque a decisão continua sendo emitida com menos informação e ninguém é
notificado.

**Coorte.** Todas as métricas de decisão quebradas pelas faixas de histórico
(`sem_historico`, `historico_minimo`, `historico_parcial`, `historico_pleno`) e pelos eixos de
equidade descritos em [MLOps](../mlops/dados-rotulos-e-promocao.md).

## Tracing e correlação

`correlation_id` propagado da borda até a auditoria, atravessando a decisão online, o evento de
challenge, o workflow de validadores e a notificação. Um caso deve ser reconstituível de ponta a
ponta a partir de um único identificador.

## Privacidade

Logs e eventos seguem as mesmas regras do
[contrato de evento](../contratos/evento-challenge.md): `subject_token` no lugar de CPF em claro,
mascaramento de campos sensíveis, minimização do que é registrado e prazo de retenção definido e
justificado por finalidade.

## Critérios de aceite

- 100% das transações registram camadas executadas, camadas não executadas, camada que encerrou e
  camada que elevou o risco — inclusive as aprovadas sem passar por modelo.
- 100% das inferências registram versões de modelo, calibração, regras e política.
- Peso efetivo aplicado ao HBOS registrado em toda transação em que o HBOS era elegível.
- Amostragem de shadow configurável entre 1% e 5%, aleatória, reprodutível e cobrindo tráfego
  dentro e fora do gate.
- Avaliação em shadow comprovadamente sem efeito sobre a decisão online, verificado por teste.
- Registro de telemetria fora do caminho síncrono, sem impacto medível no p95.
- Dashboard de convergência de versão de modelo por instância, com alerta de defasagem.
- Alerta ativo para fallback acima do limite configurado, por camada e motivo.
- Nenhum log ou evento contém CPF em claro, verificado por teste automatizado.
- Qualquer caso reconstituível de ponta a ponta a partir do `correlation_id`.
