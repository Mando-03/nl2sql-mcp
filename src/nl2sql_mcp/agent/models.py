"""Models for the ask_database agent tool.

These Pydantic models define typed inputs/outputs for the MCP tool and
the dependencies required to run the agent. They intentionally reuse
existing project models where possible to minimize redundant schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from nl2sql_mcp.models import QuerySchemaResult


class AskDatabaseResult(BaseModel):
    """Structured, decision-ready response from ask_database."""

    question: str = Field(description="Original natural language question")
    intent: str = Field(description="Short summary of the user's intent")
    clarifications_needed: list[str] = Field(
        default_factory=list, description="Follow-up questions to disambiguate the request"
    )
    schema_context: QuerySchemaResult = Field(
        description="Relevant tables and join/selection guidance used to form the query"
    )
    sql: str = Field(description="Final executed SQL normalized to the active dialect")
    execution: dict[str, int | float | str | bool] = Field(
        description=(
            "Execution metadata: dialect, elapsed_ms, row_limit, rows_returned, truncated"
        )
    )
    results: list[dict[str, str | int | float | bool | None]] = Field(
        description="Tabular results with cell values truncated as needed"
    )
    validation_notes: list[str] = Field(default_factory=list, description="SQL validation notes")
    recommended_next_steps: list[str] = Field(
        default_factory=list, description="Concrete suggestions for the caller LLM"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the SQL and results")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="UTC ISO8601 timestamp of completion",
    )
    status: Literal["ok", "error"] = Field(default="ok", description="Overall status of the call")
    execution_error: str | None = Field(
        default=None, description="Optional execution error message"
    )
    assist_notes: list[str] | None = Field(
        default=None, description="Optional guidance when an error occurred"
    )


@dataclass(slots=True)
class AgentDeps:
    """Dependencies required by the agent at runtime."""

    active_dialect: str
    row_limit: int
    max_cell_chars: int
    max_payload_bytes: int
