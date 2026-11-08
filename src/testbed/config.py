"""Loading and validating `config/models.yaml`.

Model names and prices live in YAML (never in code) so that the exact models used in an
experiment are part of its recorded configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_YAML = PROJECT_ROOT / "config" / "models.yaml"
CACHE_DIR = PROJECT_ROOT / ".cache" / "llm"


class Prices(BaseModel):
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


class ModelConfig(BaseModel):
    """One entry under `models:` in models.yaml."""

    id: str
    max_tokens: int
    effort: str | None = None
    thinking: dict[str, Any] | None = None
    price_per_mtok: Prices
    dry_run_output_tokens: int = 600


class ModelsFile(BaseModel):
    """The whole models.yaml file."""

    default: str
    max_retries: int = 5
    models: dict[str, ModelConfig]


def load_models(path: Path = MODELS_YAML) -> ModelsFile:
    """Parse and validate models.yaml."""
    return ModelsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
