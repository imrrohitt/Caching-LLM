"""Onboarding checkpoint definitions for CP WhatsApp flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Checkpoint(str, Enum):
    """Resumable atomic checkpoints (minimal 3-step flow + terminal)."""

    NAME_COLLECTION = "NAME_COLLECTION"
    PROJECT_INTEREST = "PROJECT_INTEREST"
    EOI_CONFIRMATION = "EOI_CONFIRMATION"
    COMPLETED = "COMPLETED"


# Ordered flow for progression
CHECKPOINT_ORDER: list[Checkpoint] = [
    Checkpoint.NAME_COLLECTION,
    Checkpoint.PROJECT_INTEREST,
    Checkpoint.EOI_CONFIRMATION,
    Checkpoint.COMPLETED,
]


def next_checkpoint(current: Checkpoint) -> Checkpoint | None:
    try:
        idx = CHECKPOINT_ORDER.index(current)
    except ValueError:
        return Checkpoint.NAME_COLLECTION
    if idx + 1 < len(CHECKPOINT_ORDER):
        return CHECKPOINT_ORDER[idx + 1]
    return None


@dataclass
class OnboardingData:
    cp_name: str | None = None
    project_ids: list[str] = field(default_factory=list)
    eoi_accepted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "cp_name": self.cp_name,
            "project_ids": list(self.project_ids),
            "eoi_accepted": self.eoi_accepted,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> OnboardingData:
        if not raw:
            return cls()
        return cls(
            cp_name=raw.get("cp_name"),
            project_ids=list(raw.get("project_ids") or []),
            eoi_accepted=bool(raw.get("eoi_accepted")),
        )
