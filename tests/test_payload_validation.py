from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from antifraud.domain.enums import Decision, Layer
from antifraud.validation.payload import PayloadValidationError, validate_payload
from tests.conftest import make_payload


def test_valid_payload_passes():
    payload = make_payload()
    result = validate_payload(payload)
    assert result.valid is True


def test_missing_cpf_raises_controlled_error():
    payload = make_payload(cpf="")
    with pytest.raises(PayloadValidationError) as exc_info:
        validate_payload(payload)
    assert exc_info.value.reason_code == "invalid_payload"


def test_future_timestamp_rejected():
    payload = make_payload(timestamp=datetime.now(timezone.utc) + timedelta(hours=2))
    with pytest.raises(PayloadValidationError):
        validate_payload(payload)


def test_cascade_rejects_invalid_payload_with_reject_decision(cascade):
    payload = make_payload(cpf="")
    result = cascade.decide(payload)

    assert result.decision == Decision.REJECT
    assert "invalid_payload" in result.trace.reason_codes
    assert result.trace.terminating_layer == Layer.PAYLOAD_VALIDATION
    # Nenhuma outra camada deve ter sido executada (short-circuit total).
    for layer in Layer:
        if layer == Layer.PAYLOAD_VALIDATION:
            continue
        assert layer in result.trace.skipped_layers()
