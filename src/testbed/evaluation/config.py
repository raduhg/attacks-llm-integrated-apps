"""Experiment configuration: one YAML file in config/experiments/ per experiment."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from testbed.config import PROJECT_ROOT
from testbed.defenses import KNOWN_DEFENSES


class ExperimentConfig(BaseModel):
    """Everything that defines a run of the (defense x item x repetition) matrix."""

    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")  # also the results/<id>/ folder name
    description: str = ""
    model: str | None = None  # key in config/models.yaml; None = the file's default
    repetitions: int = Field(5, ge=1)
    budget_usd: float = Field(gt=0)
    corpus: str = "clean"
    defenses: list[str] = ["D0"]
    attacks: list[Path] = []  # attack catalogue files, relative to the project root
    benign: list[Path] = []  # benign task files, relative to the project root
    max_steps: int = Field(8, ge=1)
    est_calls_per_run: float = Field(2.3, gt=0)  # dry-run estimate; ~2.3 measured in Milestones 2-3

    @field_validator("defenses")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(KNOWN_DEFENSES)
        if unknown or not v:
            raise ValueError(f"Unknown or empty defenses: {sorted(unknown)}; known: {sorted(KNOWN_DEFENSES)}")
        return v

    @field_validator("attacks", "benign")
    @classmethod
    def _exist(cls, v: list[Path]) -> list[Path]:
        missing = [p for p in v if not (PROJECT_ROOT / p).exists()]
        if missing:
            raise ValueError(f"Files not found: {missing}")
        return v


def load_experiment(path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
