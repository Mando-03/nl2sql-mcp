"""Models for the execute_query MCP tool.

Provides a minimal, decision-ready result payload for direct SQL execution
requests, without any LLM planning fields.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ExecuteQueryResult(BaseModel):
    """Structured response from the execute_query tool."""

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
        default_factory=list, description="Concrete suggestions for the caller LLM or UI"
    )
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
