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

from fastmcp.utilities.logging import get_logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent
import sqlalchemy as sa

from nl2sql_mcp.agent.models import AgentDeps, AskDatabaseResult
from nl2sql_mcp.models import QuerySchemaResult
from nl2sql_mcp.services.config_service import LLMConfig
from nl2sql_mcp.sqlglot_tools import SqlglotService
from nl2sql_mcp.sqlglot_tools.models import (
    Dialect,
    SqlAutoTranspileRequest,
    SqlValidationRequest,
)


class LlmSqlPlan(BaseModel):
    """Structured output from the LLM planning step."""

    intent: str = Field(description="Brief description of the task")
    clarifications_needed: list[str] = Field(
        default_factory=list, description="Questions that would improve the result"
    )
    sql: str = Field(description="A single executable, safe SELECT query")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence in the SQL")


_logger = get_logger(__name__)


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


def _strip_trailing_semicolon(sql: str) -> str:
    s = sql.strip()
    return s.removesuffix(";")


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
        "- Specify a LIMIT clause when appropriate.\n"
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

    _logger.info(
        "run_ask_flow: start (question=%s, dialect=%s, row_limit=%d, max_cell_chars=%d)",
        question,
        deps.active_dialect,
        deps.row_limit,
        deps.max_cell_chars,
    )

    agent = build_llm_agent(llm)
    # Build a compact prompt with schema guidance
    # Keep under model token limits; include only essentials
    table_lines: list[str] = []
    for t in schema.relevant_tables:
        cols = ", ".join(c.name for c in t.columns[:8])
        table_lines.append(f"- {t.name}: {cols}")
    total_joins = len(schema.join_examples)
    join_take = deps.row_limit // 50
    join_lines = [f"- {j.sql_syntax}" for j in schema.join_examples[:join_take]]
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

    _logger.info(
        "Prompt context prepared (tables_included=%d, joins_included=%d/%d, dialect=%s)",
        min(len(schema.relevant_tables), 10),
        len(join_lines),
        total_joins,
        deps.active_dialect,
    )

    _logger.info("Prompt prepared: %s", prompt)

    llm_result = agent.run_sync(prompt, deps=deps)
    plan = llm_result.output
    _logger.info(
        "LLM plan produced (confidence=%.2f, clarifications=%d)",
        plan.confidence,
        len(plan.clarifications_needed),
    )
    _logger.info("Planned SQL (raw): %s", plan.sql.strip())

    # Safety checks and normalization
    _enforce_select_only(plan.sql)

    # Use the SQL exactly as planned by the LLM
    plan_sql = _strip_trailing_semicolon(plan.sql)

    # Normalize and transpile to the active dialect (handles T-SQL TOP, etc.)
    trans = glot.auto_transpile_for_database(
        SqlAutoTranspileRequest(sql=plan_sql, target_dialect=cast(Dialect, deps.active_dialect))
    )
    sql_to_run = trans.sql
    if trans.notes:
        _logger.info("Transpile notes: %s", "; ".join(trans.notes))

    # Validate final SQL for the dialect and collect notes
    validation = glot.validate(
        SqlValidationRequest(sql=sql_to_run, dialect=cast(Dialect, deps.active_dialect))
    )
    notes: list[str] = []
    if trans.notes:
        notes.extend(trans.notes)
    if not validation.is_valid and validation.error_message:
        notes.append(validation.error_message)
        _logger.warning("SQL validation reported: %s", validation.error_message)
    _logger.info("SQL to execute (%s): %s", deps.active_dialect, sql_to_run)

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
    _logger.info(
        "Execution finished (elapsed_ms=%.1f, rows_returned=%d, truncated=%s)",
        elapsed_ms,
        returned,
        truncated,
    )
    _logger.info("Result columns: %s", ", ".join(cols))

    # Next-step guidance
    next_steps: list[str] = []
    if truncated:
        next_steps.append(
            "Results truncated; add WHERE filters or ask for aggregation/pagination."
        )
        _logger.warning(
            "Results truncated at row_limit=%d; suggest filtering or aggregation",
            deps.row_limit,
        )

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
