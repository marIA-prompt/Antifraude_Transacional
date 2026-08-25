# Contrato de features — schema registry

Normativo executável: [`contracts/features/registry.json`](../../contracts/features/registry.json)

## AS-IS

Duas cifras coexistem. **Nenhuma é a lista canônica.**

| Fonte | Quantidade |
|---|---|
| Apresentação AS-IS | 13 features + regras + hard-rule geográfica |
| PDF do microserviço | 10 features numéricas |

O bundle HBOS persiste perfis (média do CPF, cartões, estabelecimentos, centróide
geográfico) usados no cálculo. Isso descreve **insumos de perfil**, não a cardinalidade
final do vetor numérico.

O Motor H usa **33 features** de `FIRST_NEG83` — schema de outro problema
([motor-h-neg83.md](../recuperacao/motor-h-neg83.md)), não deste registry.

## Lacuna/Risco

Afirmar 10 ou 13 como definitivo gera contrato de modelo falso. Treino, inferência e
`feature_weights` da API v2 divergem em silêncio. Promoção sem schema versionado é o modo de
falha que o [ADR-0004](../adr/0004-publicacao-de-modelos-e-cache.md) tenta impedir.

## TO-BE

Auditoria do código de feature engineering do microserviço, seguida de:

```text
nome estável
tipo
unidade
instante de disponibilidade (anti-leakage)
dono
criticidade (nulos > 2% bloqueiam promoção)
versao do schema
```

Publicar em `contracts/features/registry.json` com `status: reconciled` e
`schema_version` semântica. Toda promoção de modelo declara `feature_schema_version`
compatível.

## Critério de aceite

- Enquanto `status = unreconciled`, este repositório **não** publica `canonical_list`.
- Critério 11 do briefing: lista canônica conciliada (10 × 13) e versionada.
- Teste automatizado em `scripts/validate_contracts.py` falha se `canonical_list` for
  preenchida sem `status: reconciled`, ou se `status` não for um dos valores do enum.
