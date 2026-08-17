"""Carregamento da configuração versionada do pipeline."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str | Path = "ml/config.yaml") -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
