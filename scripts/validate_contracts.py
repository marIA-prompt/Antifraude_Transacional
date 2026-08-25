#!/usr/bin/env python3
"""Valida os contratos versionados do motor antifraude.

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
FEATURE_REGISTRY = ROOT / "contracts/features/registry.json"

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

    scores = example.get("scores") or {}
    for layer in ("hbos", "xgb"):
        if layer in scores and scores[layer] == 0:
            fail(f"exemplo usa score {layer}=0; camada nao executada deve ser null")


def validate_openapi() -> dict:
    import yaml
    from openapi_spec_validator import validate

    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    validate(spec)
    print(f"ok  OpenAPI valido: {OPENAPI.relative_to(ROOT)}")
    return spec


def validate_v1_response_shape(spec: dict) -> None:
    schema = spec["components"]["schemas"]["ScoreResponseV1"]
    properties = set(schema.get("properties", {}))
    if properties != {"decision_final"}:
        fail(f"ScoreResponseV1 deve expor apenas decision_final, encontrado: {sorted(properties)}")
    elif schema.get("additionalProperties") is not False:
        fail("ScoreResponseV1 deve declarar additionalProperties: false")
    else:
        print("ok  contrato v1 restrito a decision_final")


def validate_v1_path(spec: dict) -> None:
    paths = spec.get("paths") or {}
    if "/api/v1/score-transaction" not in paths:
        fail("OpenAPI deve expor POST /api/v1/score-transaction (endpoint AS-IS do briefing)")
    else:
        print("ok  path AS-IS /api/v1/score-transaction presente")
    if "/api/v2/score-transaction" not in paths:
        fail("OpenAPI deve expor POST /api/v2/score-transaction")
    else:
        print("ok  path TO-BE /api/v2/score-transaction presente")


def _unique_snake(names: list[object], label: str) -> list[str]:
    if not isinstance(names, list) or not names:
        fail(f"{label} deve ser lista nao vazia")
        return []
    as_str = [n for n in names if isinstance(n, str)]
    if len(as_str) != len(names):
        fail(f"{label} deve conter apenas strings")
        return []
    if len(set(as_str)) != len(as_str):
        fail(f"{label} tem nomes duplicados")
    snake = re.compile(r"^[a-z][a-z0-9_]*$")
    bad = [n for n in as_str if not snake.match(n)]
    if bad:
        fail(f"{label} com nomes fora de snake_case: {bad}")
    if any(n.lower() in FORBIDDEN_FIELD_NAMES for n in as_str):
        fail(f"{label} contem campo de CPF em claro")
    return as_str


def validate_feature_registry() -> None:
    registry = json.loads(FEATURE_REGISTRY.read_text(encoding="utf-8"))
    status = registry.get("status")
    if status not in {"unreconciled", "candidate", "reconciled"}:
        fail(f"registry de features com status invalido: {status!r}")
        return

    counts = {src.get("id"): src.get("count_claimed") for src in registry.get("sources") or []}
    if counts.get("apresentacao_as_is") != 13 or counts.get("pdf_microservico") != 10:
        fail("registry deve registrar as duas cifras abertas (13 e 10) como fontes, nao como canonico")
    else:
        print("ok  divergencia 10 x 13 registrada como fonte, nao como lista canonica")

    if status in {"unreconciled", "candidate"}:
        if registry.get("canonical_list") is not None:
            fail(f"registry {status} nao pode publicar canonical_list")
        elif registry.get("canonical_count") is not None:
            fail(f"registry {status} nao pode publicar canonical_count")
        else:
            print(f"ok  registry de features {status} sem lista canonica")

    if status == "unreconciled":
        return

    if status == "candidate":
        ten = _unique_snake(registry.get("candidate_pdf_10") or [], "candidate_pdf_10")
        thirteen = _unique_snake(
            registry.get("candidate_apresentacao_13") or [], "candidate_apresentacao_13"
        )
        if len(ten) != 10:
            fail(f"candidate_pdf_10 deve ter 10 nomes, encontrado {len(ten)}")
        if len(thirteen) != 13:
            fail(f"candidate_apresentacao_13 deve ter 13 nomes, encontrado {len(thirteen)}")
        if ten and thirteen and thirteen[:10] != ten:
            fail("candidate_apresentacao_13 deve comecar pelos 10 da candidata PDF (hipotese H1)")
        extras = {"log_amount", "is_night", "tx_count_24h"}
        if thirteen and set(thirteen[10:]) != extras:
            fail(f"os 3 extras da apresentacao devem ser {sorted(extras)}")

        catalog = registry.get("catalog") or []
        catalog_names = [item.get("name") for item in catalog if isinstance(item, dict)]
        missing = [n for n in thirteen if n not in catalog_names]
        if missing:
            fail(f"catalogo sem definicao para: {missing}")
        else:
            print("ok  catalogo cobre as 13 candidatas")

        not_features = {item.get("code") for item in registry.get("not_features") or []}
        overlap = not_features.intersection(set(thirteen))
        if overlap:
            fail(f"reason codes misturados no vetor de features: {sorted(overlap)}")

        if registry.get("audited_production_code") is True:
            fail("status candidate nao pode marcar audited_production_code=true")
        else:
            print("ok  candidatas 10 e 13 nomeadas; producao ainda nao auditada")
        return

    canonical = registry.get("canonical_list")
    if not isinstance(canonical, list) or len(canonical) == 0:
        fail("registry reconciled exige canonical_list nao vazia")
    elif registry.get("canonical_count") != len(canonical):
        fail("canonical_count deve coincidir com o tamanho de canonical_list")
    elif registry.get("audited_production_code") is not True:
        fail("registry reconciled exige audited_production_code=true")
    else:
        print(f"ok  registry reconciled com {len(canonical)} features")


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
        registry = json.loads(FEATURE_REGISTRY.read_text(encoding="utf-8"))
    except ImportError as exc:
        print(
            f"erro: dependencia ausente ({exc.name}). "
            "Instale jsonschema, pyyaml e openapi-spec-validator."
        )
        return 2

    validate_v1_response_shape(spec)
    validate_v1_path(spec)
    validate_feature_registry()
    validate_no_plaintext_cpf(event_schema, spec, registry)

    if failures:
        print("\nfalhas:")
        for message in failures:
            print(f"  - {message}")
        return 1

    print("\ntodos os contratos validos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
