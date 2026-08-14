"""Motor de score antifraude.

Este pacote implementa o fluxo AS-IS de decisão online descrito em
``docs/CONTEXTO_OPERACIONAL.md`` e a operacionalização do ``challenge``
(Evolução prioritária 1), a invalidação de cache de modelos (Evolução
prioritária 2) e a política de cold start (Evolução prioritária 3).

Importante: HBOS e XGBoost são representados aqui como *interfaces* com
implementações de referência (stubs determinísticos). Nenhum modelo real é
treinado neste repositório -- o treinamento, a maturação de rótulos e a
validação temporal são responsabilidade do pipeline offline (fora de escopo
deste código), conforme deixado explícito na documentação operacional.
"""
