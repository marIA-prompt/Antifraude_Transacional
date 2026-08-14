#!/usr/bin/env python3
"""Valida os contratos versionados do motor antifraude.

Verifica que o JSON Schema do evento e o OpenAPI sao validos, que o exemplo
documentado do evento satisfaz o schema e que nenhum contrato aceita CPF em claro.

Uso: python3 scripts/validate_contracts.py
Dependencias: jsonschema, pyyaml, openapi-spec-validator
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENT_SCHEMA = ROOT / "contracts/events/fraud.challenge.created.schema.json"
EVENT_DOC = ROOT / "docs/contratos/evento-challenge.md"
OPENAPI = ROOT / "contracts/openapi/score-api.yaml"

# Campos que nao devem existir em contrato algum: CPF precisa trafegar tokenizado (LGPD).
FORBIDDEN_FIELD_NAMES = {"cpf", "cpf_titular", "document_number", "taxpayer_id"}

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def validate_event_schema() -> dict:
    from jsonschema import Draft202012Validator

    schema = json.loads(EVENT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    print(f"ok  JSON Schema valido: {EVENT_SCHEMA.relative_to(ROOT)}")
    return schema


def validate_event_example(schema: dict) -> None:
    from jsonschema import Draft202012Validator

    blocks = re.findall(r"```json\n(.*?)```", EVENT_DOC.read_text(encoding="utf-8"), re.S)
    if not blocks:
        fail(f"nenhum exemplo JSON encontrado em {EVENT_DOC.relative_to(ROOT)}")
        return

    example = json.loads(blocks[-1])
    errors = sorted(Draft202012Validator(schema).iter_errors(example), key=lambda e: list(e.path))
    for error in errors:
        fail(f"exemplo do evento invalido em {list(error.path)}: {error.message}")
    if not errors:
        print("ok  exemplo documentado do evento satisfaz o schema")


def validate_openapi() -> dict:
    import yaml
    from openapi_spec_validator import validate

    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    validate(spec)
    print(f"ok  OpenAPI valido: {OPENAPI.relative_to(ROOT)}")
    return spec


def validate_v1_response_shape(spec: dict) -> None:
    """A v1 deve permanecer restrita a decision_final (retrocompatibilidade)."""
    schema = spec["components"]["schemas"]["ScoreResponseV1"]
    properties = set(schema.get("properties", {}))
    if properties != {"decision_final"}:
        fail(f"ScoreResponseV1 deve expor apenas decision_final, encontrado: {sorted(properties)}")
    elif schema.get("additionalProperties") is not False:
        fail("ScoreResponseV1 deve declarar additionalProperties: false")
    else:
        print("ok  contrato v1 restrito a decision_final")


def validate_no_plaintext_cpf(*documents: object) -> None:
    found: set[str] = set()

    def walk(node: object, in_properties: bool = False) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if in_properties and key.lower() in FORBIDDEN_FIELD_NAMES:
                    found.add(key)
                walk(value, in_properties=(key == "properties"))
        elif isinstance(node, list):
            for item in node:
                walk(item, in_properties=in_properties)

    for document in documents:
        walk(document)

    if found:
        fail(f"contratos expoem CPF em claro: {sorted(found)}")
    else:
        print("ok  nenhum contrato aceita CPF em claro")


def main() -> int:
    try:
        event_schema = validate_event_schema()
        validate_event_example(event_schema)
        spec = validate_openapi()
    except ImportError as exc:
        print(f"erro: dependencia ausente ({exc.name}). Instale jsonschema, pyyaml e openapi-spec-validator.")
        return 2

    validate_v1_response_shape(spec)
    validate_no_plaintext_cpf(event_schema, spec)

    if failures:
        print("\nfalhas:")
        for message in failures:
            print(f"  - {message}")
        return 1

    print("\ntodos os contratos validos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
