"""Lightweight PydanticAI agent used by the ask_database MCP tool.

This module focuses on a minimal viable flow that:
- Uses schema_tools to plan via QuerySchemaResult
- Uses an LLM to produce a single, safe SELECT statement
- Validates/normalizes SQL to the active dialect
- Executes the query with row/size safeguards
- Returns a concise, typed payload for downstream LLM orchestration
"""

from __future__ import annotations

from collections.abc import Iterable
import time
from typing import cast

from pydantic import BaseModel, Field
from pydantic_ai import Agent
import sqlalchemy as sa

from nl2sql_mcp.agent.models import AgentDeps, AskDatabaseResult
from nl2sql_mcp.models import QuerySchemaResult
from nl2sql_mcp.services.config_service import LLMConfig
from nl2sql_mcp.sqlglot_tools import SqlglotService
from nl2sql_mcp.sqlglot_tools.models import Dialect, SqlValidationRequest


class LlmSqlPlan(BaseModel):
    """Structured output from the LLM planning step."""

    intent: str = Field(description="Brief description of the task")
    clarifications_needed: list[str] = Field(
        default_factory=list, description="Questions that would improve the result"
    )
    sql: str = Field(description="A single executable, safe SELECT query")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence in the SQL")


def _enforce_select_only(sql: str) -> None:
    """Raise ValueError if the SQL appears to include non-SELECT operations.

    This check is deliberately conservative for v1.
    """
    lowered = sql.strip().lower()
    banned: tuple[str, ...] = (
        "insert ",
        "update ",
        "delete ",
        "merge ",
        "alter ",
        "create ",
        "drop ",
        "truncate ",
        "grant ",
        "revoke ",
    )
    if any(tok in lowered for tok in banned):  # simple heuristic
        msg = "Only SELECT queries are permitted"
        raise ValueError(msg)


def _has_limit(sql: str) -> bool:
    lowered = sql.lower()
    return " limit " in lowered or lowered.rstrip().endswith(" limit")


def _truncate_value(val: object, max_chars: int) -> str | int | float | bool | None:
    """Truncate a single cell value to a safe representation."""
    if val is None:
        return None
    if isinstance(val, int | float | bool):
        return val
    s = str(val)
    if len(s) > max_chars:
        return s[: max_chars - 1] + "…"
    return s


def _truncate_rows(
    rows: Iterable[sa.RowMapping],
    columns: list[str],
    max_rows: int,
    max_chars: int,
) -> list[dict[str, str | int | float | bool | None]]:
    """Convert SQLAlchemy rows to JSON-safe dicts with truncation."""
    out: list[dict[str, str | int | float | bool | None]] = []
    for i, row in enumerate(rows):
        if i >= max_rows:
            break
        item: dict[str, str | int | float | bool | None] = {}
        for col in columns:
            item[col] = _truncate_value(row[col], max_chars)
        out.append(item)
    return out


def build_llm_agent(llm: LLMConfig) -> Agent[AgentDeps, LlmSqlPlan]:
    """Create a small PydanticAI Agent for SQL planning and generation."""

    system = (
        "You translate a user's question into a single, safe SELECT query that "
        "respects an active SQL dialect.\n"
        "Rules:\n"
        "- Output exactly one SELECT statement.\n"
        "- Do not include DDL or DML.\n"
        "- Prefer columns/tables provided in the schema context.\n"
        "- If ambiguous, choose safe defaults and list clarifications_needed.\n"
        "- Keep the query readable and minimal; avoid SELECT *.\n"
        "- Include LIMIT only if the user requests it; the caller will clamp results.\n"
    )

    model_id = f"{llm.provider}:{llm.model}" if ":" not in llm.model else llm.model

    agent: Agent[AgentDeps, LlmSqlPlan] = Agent(
        model=model_id,
        system_prompt=system,
        deps_type=AgentDeps,
        output_type=LlmSqlPlan,
        # Temperature and other settings are configured via provider environment
    )
    return agent


def run_ask_flow(
    *,
    question: str,
    schema: QuerySchemaResult,
    engine: sa.Engine,
    glot: SqlglotService,
    deps: AgentDeps,
    llm: LLMConfig,
) -> AskDatabaseResult:
    """End-to-end flow used by the ask_database tool.

    This function is synchronous for simplicity; the MCP wrapper can run it
    in the event loop thread since the DB interaction is short-lived in v1.
    """

    agent = build_llm_agent(llm)
    # Build a compact prompt with schema guidance
    # Keep under model token limits; include only essentials
    table_lines: list[str] = []
    for t in schema.relevant_tables:
        cols = ", ".join(c.name for c in t.columns[:8])
        table_lines.append(f"- {t.name}: {cols}")
    join_lines = [f"- {j.sql_syntax}" for j in schema.join_examples[: deps.row_limit // 50]]
    context = (
        "Schema context (abbrev):\n"
        + "\n".join(table_lines[:10])
        + ("\nJoins:\n" + "\n".join(join_lines) if join_lines else "")
        + f"\nDialect: {deps.active_dialect}\n"
    )

    prompt = (
        f"Question: {question}\n\n"
        f"{context}\n"
        "Return fields: intent, clarifications_needed (list), sql (single SELECT), "
        "confidence (0-1)."
    )

    llm_result = agent.run_sync(prompt, deps=deps)
    plan = llm_result.output

    # Safety checks and normalization
    _enforce_select_only(plan.sql)

    # Detect/normalize; do not force transpile across dialects here, assume same dialect
    validation = glot.validate(
        SqlValidationRequest(sql=plan.sql, dialect=cast(Dialect, deps.active_dialect))
    )
    # If invalid, keep original SQL but add note
    notes: list[str] = []
    if not validation.is_valid and validation.error_message:
        notes.append(validation.error_message)

    # Make sure a LIMIT will be enforced downstream; we will also fetchmany
    sql_to_run = plan.sql
    if not _has_limit(plan.sql):
        sql_to_run = f"{plan.sql}\nLIMIT {deps.row_limit}"

    # Execute
    elapsed_ms: float
    rows: list[dict[str, str | int | float | bool | None]]
    returned = 0
    truncated = False
    start = time.perf_counter()
    with engine.connect() as conn:
        result = conn.execute(sa.text(sql_to_run))
        cols = list(result.keys())
        map_result = result.mappings()
        raw_rows = map_result.fetchmany(deps.row_limit + 1)  # sentinel to detect truncation
        returned = min(len(raw_rows), deps.row_limit)
        truncated = len(raw_rows) > deps.row_limit
        rows = _truncate_rows(raw_rows, cols, deps.row_limit, deps.max_cell_chars)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    # Next-step guidance
    next_steps: list[str] = []
    if truncated:
        next_steps.append(
            "Results truncated; add WHERE filters or ask for aggregation/pagination."
        )
    if plan.clarifications_needed:
        next_steps.extend([f"Clarify: {q}" for q in plan.clarifications_needed])

    return AskDatabaseResult(
        question=question,
        intent=plan.intent,
        clarifications_needed=plan.clarifications_needed,
        schema_context=schema,
        sql=sql_to_run,
        execution={
            "dialect": deps.active_dialect,
            "elapsed_ms": elapsed_ms,
            "row_limit": deps.row_limit,
            "rows_returned": returned,
            "truncated": truncated,
        },
        results=rows,
        validation_notes=notes,
        recommended_next_steps=next_steps,
        confidence=plan.confidence,
        status="ok",
    )
