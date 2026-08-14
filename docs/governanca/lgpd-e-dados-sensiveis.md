# LGPD, dados sensíveis e exposição da lógica antifraude

Endereça `LR-12` e `LR-13`. Antifraude tem base legal robusta (prevenção à fraude, legítimo interesse
e obrigações regulatórias), o que **não** dispensa minimização, finalidade declarada, retenção
limitada e controle de acesso.

## 1. Dados pessoais no fluxo

| Dado | Onde aparece | Tratamento alvo |
| --- | --- | --- |
| CPF | payload, chave do bundle HBOS, evento, trace | Tokenizado em evento, trace e fila; valor original apenas onde a finalidade exige |
| Identificador interno | evento, trace | Preferido sobre CPF em toda a trilha assíncrona |
| Geolocalização | features, regras, evidências | Precisão reduzida ao necessário para a regra; não persistir coordenada bruta além da finalidade |
| Device fingerprint | features, regras | Pseudonimizado; sem dado que permita reidentificação além do necessário |
| Contato para step-up (telefone/WhatsApp) | trilha de challenge | Acesso restrito ao componente de notificação; não replicado no trace |
| Histórico transacional | bundle HBOS, features | Janela declarada (até ~730 dias) com expurgo ao final |
| Evidências e reason codes | auditoria | Retidos pelo prazo de contestação e obrigação legal |

## 2. Princípios aplicados ao desenho

- **Minimização no evento.** `fraud.challenge.created` transporta o necessário para o validador
  decidir, não o payload inteiro. Feature relevante, não todas as features.
- **Tokenização por padrão** em evento, fila e trace. A trilha assíncrona é o local com mais cópias e
  mais consumidores, logo é onde o dado bruto causa mais dano.
- **Finalidade por consumidor.** Cada consumidor de evento/API declara finalidade e recebe o
  subconjunto compatível com ela.
- **Retenção declarada por artefato**, com expurgo automatizado: trace, evento, contexto de challenge,
  bundle e dataset de treino têm prazos próprios e justificados.
- **Segregação de acesso.** Score, features e pesos são dados de risco: acesso auditado, não
  disponível a qualquer serviço interno por conveniência.
- **Auditoria de acesso**, não apenas de decisão: quem leu explicabilidade de qual transação.

## 3. Direitos do titular e decisão automatizada

A decisão de negar uma transação é automatizada e o titular pode pedir revisão. O desenho precisa
sustentar isso:

- **Explicabilidade reconstruível** a partir do trace e das evidências, com a versão de modelo e a
  versão de política vigentes no momento da decisão (por isso `model_version` e `policy_version` são
  obrigatórios).
- **Revisão humana disponível** — é o papel do `escalate` na
  [Evolução 1](../evolucoes/01-challenge-operacional.md).
- **Reason code compreensível** ao titular, distinto do detalhe técnico interno.

## 4. Exposição da lógica antifraude

Explicabilidade e segurança tensionam entre si: o detalhe que ajuda a auditar também ensina a burlar.
Resolver por perfil, não por endpoint único.

| Perfil | Recebe | Não recebe |
| --- | --- | --- |
| Canal externo / cliente | `decision_final`, reason code agregado e compreensível | score, threshold, nome de regra, peso de feature, versão de modelo |
| Operação de fraude / analista | score, sinais, reason codes, evidências, features relevantes | dado pessoal além do necessário para o caso |
| Auditoria / risco | conjunto completo, com trilha de acesso | — |
| Ciência de dados | features e scores pseudonimizados, em base analítica | dado de contato, identificador direto |

Regras firmes:

- **v1 permanece intocada** com `decision_final`, garantindo retrocompatibilidade e evitando que
  consumidor não autorizado receba detalhe por acidente de versão.
- **v2 exige autenticação e autorização por perfil**, com mascaramento aplicado no serviço, nunca
  delegado ao consumidor.
- **Nenhuma mensagem ao cliente revela a regra acionada.** "Confirme esta compra" não deve informar
  qual sinal disparou.
- **Erro não vaza lógica.** Mensagem de erro e código HTTP não devem permitir inferir threshold ou
  regra por tentativa e erro.
- **Rate limit e detecção de sondagem** na v2: consulta repetida de explicabilidade é vetor de
  engenharia reversa do motor.

## Critérios de aceite

| # | Critério | Como comprovar |
| --- | --- | --- |
| CA-L.1 | CPF tokenizado na trilha assíncrona | Inspeção de amostra de eventos e traces: zero ocorrências de CPF em claro |
| CA-L.2 | Retenção declarada e aplicada por artefato | Política documentada por artefato e evidência de expurgo executado |
| CA-L.3 | v2 com autenticação, autorização por perfil e mascaramento | Testes de contrato por perfil: perfil externo não recebe campos restritos |
| CA-L.4 | v1 retrocompatível | Suíte de contrato v1 passa sem alteração após a introdução da v2 |
| CA-L.5 | Explicabilidade reconstruível | Para amostra de decisões, reconstruir a explicação com `model_version` e `policy_version` do momento |
| CA-L.6 | Acesso à explicabilidade auditado | Log de acesso por consumidor e transação, com retenção definida |
| CA-L.7 | Mensagem de step-up não revela regra | Revisão dos templates de notificação |
| CA-L.8 | Rate limit ativo na v2 | Teste de carga confirma limite e alerta de sondagem |
