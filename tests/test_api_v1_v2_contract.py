from __future__ import annotations

from fastapi.testclient import TestClient

from antifraud.api.app import create_app


def _payload(**overrides):
    base = {
        "transaction_id": "tx-100",
        "correlation_id": "corr-100",
        "cpf": "12345678900",
        "amount": 100.0,
    }
    base.update(overrides)
    return base


def test_v1_response_exposes_only_decision_final():
    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/transactions/authorize", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"decision_final"}
    assert body["decision_final"] in {"approve", "challenge", "deny", "escalate", "reject"}


def test_v2_requires_authentication():
    app = create_app()
    client = TestClient(app)

    response = client.post("/v2/transactions/authorize", json=_payload())
    assert response.status_code == 401


def test_v2_analyst_receives_full_explainability_payload():
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v2/transactions/authorize",
        json=_payload(transaction_id="tx-101", correlation_id="corr-101"),
        headers={"X-API-Key": "demo-analyst-key"},
    )

    assert response.status_code == 200
    body = response.json()
    for field in ["score", "decision", "signals", "features", "feature_weights", "reason_codes"]:
        assert field in body
    assert isinstance(body["features"], dict) and len(body["features"]) > 0
    assert isinstance(body["model_versions"], dict) and len(body["model_versions"]) > 0


def test_v2_basic_role_receives_masked_payload():
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v2/transactions/authorize",
        json=_payload(transaction_id="tx-102", correlation_id="corr-102"),
        headers={"X-API-Key": "demo-basic-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["features"] == {}
    assert body["feature_weights"] == {}
    assert body["model_versions"] == {}
    # Campos de decisão continuam visíveis mesmo mascarado.
    assert body["decision"] in {"approve", "challenge", "deny", "escalate", "reject"}


def test_v1_and_v2_agree_on_underlying_decision_for_same_transaction():
    app = create_app()
    client = TestClient(app)
    payload = _payload(transaction_id="tx-200", correlation_id="corr-200", amount=9999999.0)

    v1_response = client.post("/v1/transactions/authorize", json=payload)
    payload_v2 = dict(payload)
    payload_v2["transaction_id"] = "tx-201"
    payload_v2["correlation_id"] = "corr-201"
    v2_response = client.post(
        "/v2/transactions/authorize",
        json=payload_v2,
        headers={"X-API-Key": "demo-admin-key"},
    )

    assert v1_response.json()["decision_final"] == v2_response.json()["decision"]
