import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _walk_keys(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            yield path, key, value
            yield from _walk_keys(value, path)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item, prefix)


def test_event_schemas_forbid_cpf_field():
    for path in CONTRACTS.rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for json_path, key, _value in _walk_keys(data):
            assert key.lower() != "cpf", f"campo cpf encontrado em {path}: {json_path}"
            assert "cpf" not in key.lower() or key == "subject_id", (
                f"identificador cpf em {path}: {json_path}"
            )


def test_openapi_v1_response_only_decision_final():
    text = (CONTRACTS / "openapi" / "v1.yaml").read_text(encoding="utf-8")
    assert "decision_final" in text
    assert "feature_weights" not in text.split("ScoreResponseV1")[1].split("ControlledError")[0]
