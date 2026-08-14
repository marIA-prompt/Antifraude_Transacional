# Evolução prioritária 3 — Política de cold start

Endereça `LR-05` e `LR-14`.

## AS-IS

- O HBOS é individual por CPF e depende de histórico (janela de até aproximadamente 730 dias).
- CPF novo, ou com histórico insuficiente, não tem base comportamental própria.
- A aprovação padrão nesse cenário reduz atrito.
- O XGBoost global é o componente que cobre esse caso, por aprender padrões globais.

## Lacuna / Risco

A aprovação padrão de CPF novo reduz atrito e **aumenta exposição** exatamente onde o atacante
prefere operar: conta nova, sem histórico, sem sinal comportamental disponível. É o cenário clássico
de teste de cartão e de fraude de aquisição.

Há um segundo risco, de sinal oposto e menos óbvio: quando o HBOS é aplicado sobre histórico
insuficiente, ele produz anomalia espúria. Com dois ou três pontos de referência, quase tudo é
atípico. Isso penaliza cliente novo legítimo com `challenge` ou `deny` por artefato estatístico, não
por risco — um viés estrutural contra quem acabou de entrar (ver
[viés e equidade](../mlops/vies-e-equidade.md)).

Ou seja, tratar cold start como "aprova por padrão" e tratar como "usa HBOS de qualquer forma" estão
ambos errados, por motivos diferentes.

## TO-BE

A política de cold start é **configurável** por valor, canal, produto, tipo de transação, hard rules
e confiança disponível — e alterável sem redeploy.

### Confiança do histórico como variável explícita

Em vez do binário "CPF novo / CPF antigo", a decisão usa um nível de confiança derivado de volume de
transações, extensão e recência do histórico:

| Nível | Critério (parametrizável) | Peso do HBOS | Peso do modelo global |
| --- | --- | --- | --- |
| `none` | sem histórico utilizável | 0 | máximo |
| `low` | histórico curto ou esparso | reduzido | elevado |
| `medium` | histórico parcial | intermediário | intermediário |
| `high` | histórico consistente na janela | pleno | referência |

Toda transação com nível `none` ou `low` carrega o reason code `RC_COLD_START`, que precisa aparecer
na explicabilidade e nas métricas por coorte.

### Matriz de decisão de referência

```text
CPF novo + baixo valor + sem hard rule
→ approve com monitoramento reforçado

CPF novo + valor intermediário
→ challenge com step-up

CPF novo + alto valor ou hard rule crítica
→ deny ou escalate
```

Complementos que a matriz precisa contemplar, por serem os vetores reais em cold start:

- **velocidade**: várias tentativas em curta janela pelo mesmo device, cartão, IP ou estabelecimento
  não é caso de "baixo valor aprovado", ainda que cada transação isolada seja pequena;
- **acumulado**: soma de aprovações de baixo valor na janela precisa de limite próprio, senão o
  fracionamento burla o critério de valor;
- **canal e produto**: o mesmo valor tem risco diferente por canal.

### Configuração sem redeploy

Thresholds, limites por faixa e pesos por nível de confiança vivem em configuração versionada com:

- validação de schema antes de aplicar;
- versão da configuração registrada em cada decisão (`policy_version` no trace);
- trilha de auditoria de quem alterou, quando e qual o valor anterior;
- rollback para a configuração anterior.

Configuração que decide risco é código: precisa de revisão, versão e rollback, não de edição direta
em painel sem rastro.

## Critérios de aceite

| # | Critério | Como comprovar |
| --- | --- | --- |
| CA-3.1 | Métricas separadas para CPF novo e CPF com histórico | Painel segmentado por nível de confiança (`none`/`low`/`medium`/`high`) com todas as taxas principais |
| CA-3.2 | Taxas por coorte: fraude, `challenge`, `deny`, aprovação legítima e reversão | Relatório periódico por coorte, com intervalo de confiança e volume mínimo declarado |
| CA-3.3 | Thresholds configuráveis sem redeploy | Alteração aplicada em ambiente controlado com efeito medido e sem release; `policy_version` muda no trace |
| CA-3.4 | Revisão periódica de impacto em atrito, receita e perda por fraude | Ata de revisão recorrente com as três dimensões e decisão registrada (manter, ajustar, reverter) |
| CA-3.5 | Peso do HBOS reduzido ou nulo sob histórico insuficiente | Teste: transação de CPF sem histórico não recebe contribuição do HBOS; `feature_weights` comprova |
| CA-3.6 | `RC_COLD_START` presente | 100% das decisões com confiança `none`/`low` carregam o reason code |
| CA-3.7 | Controle de fracionamento | Teste de cenário: N transações de baixo valor na janela escalam para `challenge` em vez de aprovarem individualmente |

## Métricas

Sempre segmentadas por nível de confiança do histórico:

- taxa de fraude confirmada e fraude residual;
- taxa de `challenge`, `deny` e aprovação legítima;
- taxa de reversão após step-up e após análise humana (mede falso positivo);
- ticket médio e valor exposto aprovado por coorte;
- FPR e FNR por coorte, comparados entre `none`/`low` e `high` — divergência sistemática é sinal de
  viés estrutural, não de risco real;
- proporção de CPF novo no volume total (também é sinal de ataque quando salta).

## Rollout

1. Instrumentar o nível de confiança do histórico e `RC_COLD_START` **sem alterar decisão**. Medir a
   distribuição real das coortes.
2. Aplicar os pesos por confiança (HBOS reduzido/nulo) em shadow, comparando o score consolidado
   contra o atual.
3. Ativar a matriz de decisão em uma faixa estreita de valor e um canal, com step-up disponível.
4. Expandir por canal e produto, revisando atrito e perda a cada expansão.
5. Rollback: reverter `policy_version` para a configuração anterior.

## Riscos da própria evolução

- **Atrito em aquisição.** Endurecer cold start afeta diretamente cliente novo legítimo, com impacto
  comercial mensurável. Por isso CA-3.4 exige revisão conjunta de atrito, receita e perda — não
  apenas de fraude evitada.
- **Fraudador aquecendo conta.** Se o critério de confiança for simples demais (por exemplo, apenas
  contagem de transações), o atacante constrói histórico barato antes do golpe. Recência, dispersão
  de valor e diversidade de estabelecimento mitigam.
- **Coorte com volume baixo** produz métrica instável: relatórios precisam declarar volume mínimo
  antes de concluir diferença entre coortes.
