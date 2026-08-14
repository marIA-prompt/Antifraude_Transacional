from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from antifraud.domain.models import TransactionPayload


class PayloadValidationError(Exception):
    """Erro controlado de validação de payload (AS-IS: 'Rejeitar / erro controlado')."""

    def __init__(self, reason_code: str, message: str):
        self.reason_code = reason_code
        self.message = message
        super().__init__(f"{reason_code}: {message}")


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_payload(payload: TransactionPayload) -> ValidationResult:
    """Validação de schema, campos obrigatórios, tipos, idempotência e saneamento.

    Levanta ``PayloadValidationError`` (reason_code auditável) quando a
    transação deve ser rejeitada antes de qualquer cálculo de risco.
    """

    errors: list[str] = []

    if not payload.transaction_id.strip():
        errors.append("transaction_id vazio")
    if not payload.correlation_id.strip():
        errors.append("correlation_id vazio")
    if not payload.cpf.strip():
        errors.append("cpf ausente")
    if payload.amount is None or payload.amount < 0:
        errors.append("amount inválido")

    now = datetime.now(timezone.utc)
    ts = payload.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ts > now.replace(microsecond=0) and (ts - now).total_seconds() > 60:
        errors.append("timestamp futuro (fora de tolerância)")

    if payload.geolocation is not None:
        lat = payload.geolocation.get("lat")
        lon = payload.geolocation.get("lon")
        if lat is not None and not (-90.0 <= lat <= 90.0):
            errors.append("latitude fora de faixa")
        if lon is not None and not (-180.0 <= lon <= 180.0):
            errors.append("longitude fora de faixa")

    if errors:
        raise PayloadValidationError(reason_code="invalid_payload", message="; ".join(errors))

    return ValidationResult(valid=True, errors=[])
