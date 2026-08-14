"""Outbox for fraud.challenge.created — idempotent by transaction_id + correlation_id."""

from __future__ import annotations

from datetime import datetime, timezone

from antifraud.models import DecisionResult, Transaction


class ChallengeOutbox:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], dict] = {}

    def __len__(self) -> int:
        return len(self._events)

    def events(self) -> list[dict]:
        return list(self._events.values())

    def get(self, transaction_id: str, correlation_id: str) -> dict | None:
        return self._events.get((transaction_id, correlation_id))

    def publish(self, tx: Transaction, result: DecisionResult) -> dict | None:
        if result.decision != "challenge":
            return None
        key = (tx.transaction_id, tx.correlation_id)
        if key in self._events:
            return self._events[key]
        event = {
            "event_name": "fraud.challenge.created",
            "event_version": "1.0.0",
            "transaction_id": tx.transaction_id,
            "correlation_id": tx.correlation_id,
            "subject_id": tx.subject_id,
            "timestamp": tx.timestamp or datetime.now(timezone.utc).isoformat(),
            "score_hbos": result.score_hbos,
            "score_xgboost": result.score_xgboost,
            "score_consolidated": result.score,
            "signals": list(result.signals),
            "rules_triggered": [s for s in result.signals if s.startswith("rule_")],
            "features_relevant": dict(result.features),
            "model_versions": result.model_versions.as_dict(),
            "layers_executed": list(result.layers_executed),
            "terminated_by": result.terminated_by,
            "initial_decision": "challenge",
            "validator_context": {
                "channel": tx.channel,
                "product": tx.product,
                "amount": tx.amount,
                "history_days": tx.history_days,
            },
        }
        self._events[key] = event
        return event
