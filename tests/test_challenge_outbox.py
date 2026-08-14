from antifraud.cache import ModelCache
from antifraud.challenge import ChallengeOutbox
from antifraud.engine import ScoreEngine
from antifraud.models import Transaction
from antifraud.policy import PolicyConfig

POLICY = PolicyConfig.load()


def engine() -> ScoreEngine:
    return ScoreEngine(POLICY, cache=ModelCache(), outbox=ChallengeOutbox())


def test_challenge_emits_single_idempotent_event():
    svc = engine()
    t = Transaction(
        transaction_id="tx-ch",
        correlation_id="corr-ch",
        subject_id="tok_1",
        amount=80.0,
        timestamp="2026-08-14T12:00:00Z",
        history_days=400,
        injected_hbos=0.5,
        injected_xgboost=0.55,
    )
    first = svc.score(t)
    second = svc.score(t)
    assert first.decision == "challenge"
    assert second.decision == "challenge"
    assert len(svc.outbox) == 1
    event = svc.outbox.get("tx-ch", "corr-ch")
    assert event is not None
    assert event["event_name"] == "fraud.challenge.created"
    assert event["initial_decision"] == "challenge"
    assert event["subject_id"] == "tok_1"
    assert "cpf" not in event
    assert event["model_versions"]["hbos"]
    assert event["model_versions"]["xgboost"]


def test_approve_does_not_publish_challenge():
    svc = engine()
    svc.score(
        Transaction(
            transaction_id="tx-ok",
            correlation_id="corr-ok",
            subject_id="tok_2",
            amount=40.0,
            timestamp="2026-08-14T12:00:00Z",
            history_days=400,
            injected_hbos=0.05,
            injected_xgboost=0.05,
        )
    )
    assert len(svc.outbox) == 0


def test_hot_path_has_no_automl_or_agents():
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/antifraud/engine.py").read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    assert "azure" not in imported
    assert "azureml" not in imported
    assert "agent_framework" not in imported
    assert "openai" not in imported
