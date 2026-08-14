"""Configurable cold-start and consolidation thresholds. Reloaded without redeploy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).with_name("policy.default.json")


@dataclass(frozen=True)
class PolicyConfig:
    low_value_max: float
    mid_value_max: float
    approve_max: float
    challenge_max: float
    thin_file_days: int
    shadow_rate: float
    hbos_new_subject_weight: float
    hbos_weight: float
    xgboost_weight: float
    policy_version: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyConfig":
        return cls(
            low_value_max=float(data["low_value_max"]),
            mid_value_max=float(data["mid_value_max"]),
            approve_max=float(data["approve_max"]),
            challenge_max=float(data["challenge_max"]),
            thin_file_days=int(data["thin_file_days"]),
            shadow_rate=float(data["shadow_rate"]),
            hbos_new_subject_weight=float(data["hbos_new_subject_weight"]),
            hbos_weight=float(data["hbos_weight"]),
            xgboost_weight=float(data["xgboost_weight"]),
            policy_version=str(data["policy_version"]),
        )

    @classmethod
    def load(cls, path: str | Path | None = None) -> "PolicyConfig":
        with Path(path or DEFAULT_PATH).open(encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
