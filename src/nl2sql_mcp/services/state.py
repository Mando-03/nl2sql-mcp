"""Typed initialization state for schema service.

Internal module providing strongly-typed lifecycle state for
`SchemaServiceManager`. Not exposed outside the process.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Final


class SchemaInitPhase(Enum):
    """Initialization phase for the schema service lifecycle."""

    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    READY = auto()
    FAILED = auto()
    STOPPED = auto()


@dataclass(frozen=True)
class SchemaInitState:
    """Snapshot of initialization state with timestamps and error details."""

    phase: SchemaInitPhase
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str | None = None
    attempts: int = 0


# Convenience constants for call sites
INIT_NOT_READY_PHASES: Final[set[SchemaInitPhase]] = {
    SchemaInitPhase.IDLE,
    SchemaInitPhase.STARTING,
    SchemaInitPhase.RUNNING,
}
