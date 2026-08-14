#!/usr/bin/env python3
"""Valida os contratos do motor antifraude.

Verificacoes:
  1. cada schema em docs/contratos/schemas e um JSON Schema 2020-12 valido;
  2. cada exemplo em docs/contratos/exemplos valida contra o schema correspondente;
  3. os arquivos OpenAPI fazem parse e mantem as invariantes de contrato (v1 so expoe
     decision_final; v2 exige autenticacao em todas as operacoes);
  4. todo reason code usado nos exemplos existe no catalogo reason-codes.md;
  5. score de camada nao executada e null, nunca 0;
  6. os schemas rejeitam violacoes das invariantes de projeto (testes negativos).

Uso: python3 tools/validate_contracts.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = REPO_ROOT / "docs" / "contratos"
SCHEMAS_DIR = CONTRACTS / "schemas"
EXAMPLES_DIR = CONTRACTS / "exemplos"
REASON_CODES_DOC = CONTRACTS / "reason-codes.md"

# Prefixo do arquivo de exemplo -> schema correspondente.
EXAMPLE_TO_SCHEMA = {
    "decision-trace": "decision-trace.schema.json",
    "fraud.challenge.created": "fraud.challenge.created.schema.json",
    "validator-result": "validator-result.schema.json",
    "challenge.outcome.recorded": "challenge.outcome.recorded.schema.json",
    "model.published": "model.published.schema.json",
}

REASON_CODE_RE = re.compile(r"\bRC_[A-Z0-9_]{2,48}\b")

failures: list[str] = []
checks = 0


def fail(message: str) -> None:
    failures.append(message)
    print(f"  FALHOU: {message}")


def ok(message: str) -> None:
    global checks
    checks += 1
    print(f"  ok: {message}")


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def schema_for(example_path: Path) -> Path | None:
    name = example_path.name
    for prefix, schema_name in EXAMPLE_TO_SCHEMA.items():
        if name.startswith(prefix):
            return SCHEMAS_DIR / schema_name
    return None


def collect_reason_codes(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for value in node.values():
            found |= collect_reason_codes(value)
    elif isinstance(node, list):
        for item in node:
            found |= collect_reason_codes(item)
    elif isinstance(node, str) and REASON_CODE_RE.fullmatch(node):
        found.add(node)
    return found


def validate_schemas() -> None:
    print("\n[1] Schemas contra o metaschema 2020-12")
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("  aviso: jsonschema nao instalado; instale com requirements-dev.txt")
        fail("jsonschema ausente: validacao estrutural nao executada")
        return

    for schema_path in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        try:
            schema = load_json(schema_path)
            Draft202012Validator.check_schema(schema)
            ok(f"{schema_path.name} e um schema valido")
        except Exception as exc:  # noqa: BLE001 - relatorio agregado
            fail(f"{schema_path.name}: {exc}")


def validate_examples() -> None:
    print("\n[2] Exemplos contra os schemas")
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fail("jsonschema ausente: exemplos nao validados")
        return

    examples = sorted(EXAMPLES_DIR.glob("*.json"))
    if not examples:
        fail("nenhum exemplo encontrado")
        return

    for example_path in examples:
        schema_path = schema_for(example_path)
        if schema_path is None:
            fail(f"{example_path.name}: nenhum schema mapeado")
            continue
        validator = Draft202012Validator(load_json(schema_path))
        errors = sorted(validator.iter_errors(load_json(example_path)), key=lambda e: list(e.path))
        if errors:
            for error in errors:
                location = "/".join(str(part) for part in error.path) or "(raiz)"
                fail(f"{example_path.name} em {location}: {error.message}")
        else:
            ok(f"{example_path.name} valida contra {schema_path.name}")


def validate_openapi() -> None:
    print("\n[3] Contratos OpenAPI")
    try:
        import yaml
    except ImportError:
        fail("pyyaml ausente: OpenAPI nao validado")
        return

    v1_path = CONTRACTS / "openapi-v1.yaml"
    v2_path = CONTRACTS / "openapi-v2.yaml"

    for path in (v1_path, v2_path):
        if not path.exists():
            fail(f"{path.name} nao encontrado")
            return

    v1 = yaml.safe_load(v1_path.read_text(encoding="utf-8"))
    v2 = yaml.safe_load(v2_path.read_text(encoding="utf-8"))

    for name, spec in (("openapi-v1.yaml", v1), ("openapi-v2.yaml", v2)):
        if not spec.get("openapi", "").startswith("3."):
            fail(f"{name}: versao OpenAPI ausente ou nao suportada")
        elif not spec.get("paths"):
            fail(f"{name}: nenhum path declarado")
        else:
            ok(f"{name} faz parse e declara paths")

    v1_response = (
        v1.get("components", {}).get("schemas", {}).get("ScoreResponseV1", {}).get("properties", {})
    )
    if set(v1_response) != {"decision_final"}:
        fail(f"openapi-v1.yaml: resposta v1 deve expor apenas decision_final, encontrado {sorted(v1_response)}")
    else:
        ok("openapi-v1.yaml: resposta v1 restrita a decision_final")

    for path, operations in v2.get("paths", {}).items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not operation.get("security"):
                fail(f"openapi-v2.yaml: {method.upper()} {path} sem security declarado")
            else:
                ok(f"openapi-v2.yaml: {method.upper()} {path} exige autenticacao")


def validate_reason_codes() -> None:
    print("\n[4] Reason codes usados existem no catalogo")
    if not REASON_CODES_DOC.exists():
        fail("reason-codes.md nao encontrado")
        return

    catalog = set(REASON_CODE_RE.findall(REASON_CODES_DOC.read_text(encoding="utf-8")))
    if not catalog:
        fail("catalogo de reason codes vazio")
        return

    used: set[str] = set()
    for example_path in sorted(EXAMPLES_DIR.glob("*.json")):
        used |= collect_reason_codes(load_json(example_path))

    unknown = sorted(used - catalog)
    if unknown:
        fail(f"reason codes fora do catalogo: {', '.join(unknown)}")
    else:
        ok(f"{len(used)} reason codes usados, todos catalogados")


def validate_null_scores() -> None:
    print("\n[5] Camada nao executada tem score null, nunca 0")
    for example_path in sorted(EXAMPLES_DIR.glob("decision-trace*.json")):
        trace = load_json(example_path)
        skipped = {
            entry["layer"]
            for entry in trace.get("layers", [])
            if entry.get("status") in {"skipped", "failed"}
        }
        scores = trace.get("scores", {})
        layer_of_score = {"hbos": "hbos_individual", "xgboost": "xgboost_global"}
        problems = [
            key
            for key, layer in layer_of_score.items()
            if layer in skipped and scores.get(key) is not None
        ]
        if problems:
            fail(f"{example_path.name}: score presente para camada nao executada: {problems}")
        else:
            ok(f"{example_path.name}: scores coerentes com as camadas executadas")


REMOVE = object()


def mutate(base: dict, path: tuple, value: object) -> dict:
    """Copia rasa suficiente para alterar um campo aninhado sem tocar o original."""
    clone = json.loads(json.dumps(base))
    target = clone
    for key in path[:-1]:
        target = target[key]
    if value is REMOVE:
        target.pop(path[-1], None)
    else:
        target[path[-1]] = value
    return clone


def validate_negative_cases() -> None:
    print("\n[6] Testes negativos: schemas rejeitam violacoes de invariante")
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        fail("jsonschema ausente: testes negativos nao executados")
        return

    trace = load_json(EXAMPLES_DIR / "decision-trace.challenge-cold-start.json")
    validator_result = load_json(EXAMPLES_DIR / "validator-result.blocklist-timeout-fallback.json")
    published = load_json(EXAMPLES_DIR / "model.published.json")
    challenge_event = load_json(EXAMPLES_DIR / "fraud.challenge.created.json")

    cases = [
        (
            "decision trace sem reason code",
            "decision-trace.schema.json",
            mutate(trace, ("reason_codes",), []),
        ),
        (
            "decision trace com camada desconhecida",
            "decision-trace.schema.json",
            mutate(trace, ("terminal_layer",), "camada_inexistente"),
        ),
        (
            "decision trace com CPF em claro no lugar do token",
            "decision-trace.schema.json",
            mutate(trace, ("subject", "cpf_token"), "12345678901"),
        ),
        (
            "validador em timeout sem fallback declarado",
            "validator-result.schema.json",
            mutate(validator_result, ("fallback_applied",), False),
        ),
        (
            "encerramento antecipado sem deny de alta confianca",
            "validator-result.schema.json",
            mutate(
                mutate(validator_result, ("terminates_workflow",), True),
                ("outcome",),
                "escalate",
            ),
        ),
        (
            "publicacao com artefato nao verificado",
            "model.published.schema.json",
            mutate(published, ("artifact", "integrity_verified"), False),
        ),
        (
            "publicacao com schema de features incompativel",
            "model.published.schema.json",
            mutate(published, ("feature_schema", "compatible"), False),
        ),
        (
            "promocao a champion sem metricas de validacao",
            "model.published.schema.json",
            mutate(published, ("validation_metrics",), REMOVE),
        ),
        (
            "invalidacao by_key sem lista de chaves",
            "model.published.schema.json",
            mutate(published, ("cache_invalidation", "scope"), "by_key"),
        ),
        (
            "evento de challenge sem chave de idempotencia",
            "fraud.challenge.created.schema.json",
            mutate(challenge_event, ("idempotency_key",), REMOVE),
        ),
        (
            "evento de challenge com decisao inicial diferente de challenge",
            "fraud.challenge.created.schema.json",
            mutate(challenge_event, ("initial_decision",), "deny"),
        ),
    ]

    for description, schema_name, payload in cases:
        validator = Draft202012Validator(load_json(SCHEMAS_DIR / schema_name))
        if validator.is_valid(payload):
            fail(f"schema aceitou payload invalido: {description}")
        else:
            ok(f"rejeitado como esperado: {description}")


def main() -> int:
    print("Validacao de contratos — motor antifraude")
    validate_schemas()
    validate_examples()
    validate_openapi()
    validate_reason_codes()
    validate_null_scores()
    validate_negative_cases()

    print(f"\n{checks} verificacoes ok, {len(failures)} falhas")
    if failures:
        print("\nFalhas:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
