"""Execution flow for the execute_query MCP tool.

This module provides a small, dependency-injected runner that:
- Enforces SELECT-only policy
- Normalizes/transpiles SQL to the active dialect
- Validates SQL with sqlglot
- Executes via SQLAlchemy with row and cell truncation safeguards
- Returns a concise, typed result payload
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import time

from fastmcp.utilities.logging import get_logger
import sqlalchemy as sa

from nl2sql_mcp.execute.models import ExecuteQueryResult
from nl2sql_mcp.sqlglot_tools import SqlglotService
from nl2sql_mcp.sqlglot_tools.models import Dialect, SqlAutoTranspileRequest, SqlValidationRequest

_logger = get_logger(__name__)


def enforce_select_only(sql: str) -> None:
    """Raise ValueError when the SQL appears to include non-SELECT operations."""
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
    if any(tok in lowered for tok in banned):  # conservative heuristic
        msg = "Only SELECT queries are permitted"
        raise ValueError(msg)


def strip_trailing_semicolon(sql: str) -> str:
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
    """Convert rows to JSON-safe dicts with truncation and row limit."""
    out: list[dict[str, str | int | float | bool | None]] = []
    for i, row in enumerate(rows):
        if i >= max_rows:
            break
        item: dict[str, str | int | float | bool | None] = {}
        for col in columns:
            item[col] = _truncate_value(row[col], max_chars)
        out.append(item)
    return out


@dataclass(slots=True)
class ExecutionLimits:
    """Execution limits used to bound row count and cell size."""

    row_limit: int
    max_cell_chars: int


def run_execute_flow(
    *,
    sql: str,
    engine: sa.Engine,
    glot: SqlglotService,
    active_dialect: Dialect,
    limits: ExecutionLimits,
) -> ExecuteQueryResult:
    """Execute a caller-provided SELECT with normalization and validation.

    Designed to be short and dependency-injected for easy testing.
    """

    _logger.info(
        "run_execute_flow: start (dialect=%s, row_limit=%d, max_cell_chars=%d)",
        active_dialect,
        limits.row_limit,
        limits.max_cell_chars,
    )

    # Policy and normalization
    enforce_select_only(sql)
    base_sql = strip_trailing_semicolon(sql)

    trans = glot.auto_transpile_for_database(
        SqlAutoTranspileRequest(sql=base_sql, target_dialect=active_dialect)
    )
    sql_to_run = trans.sql

    validation = glot.validate(SqlValidationRequest(sql=sql_to_run, dialect=active_dialect))
    notes: list[str] = []
    if trans.notes:
        notes.extend(trans.notes)
    if not validation.is_valid and validation.error_message:
        notes.append(validation.error_message)
        _logger.warning("SQL validation reported: %s", validation.error_message)

    _logger.info("SQL to execute (%s): %s", active_dialect, sql_to_run)

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
        raw_rows = map_result.fetchmany(limits.row_limit + 1)  # sentinel to detect truncation
        returned = min(len(raw_rows), limits.row_limit)
        truncated = len(raw_rows) > limits.row_limit
        rows = _truncate_rows(raw_rows, cols, limits.row_limit, limits.max_cell_chars)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    _logger.info(
        "Execution finished (elapsed_ms=%.1f, rows_returned=%d, truncated=%s)",
        elapsed_ms,
        returned,
        truncated,
    )

    next_steps: list[str] = []
    if truncated:
        next_steps.append(
            "Results truncated; add WHERE filters or ask for aggregation/pagination."
        )

    return ExecuteQueryResult(
        sql=sql_to_run,
        execution={
            "dialect": active_dialect,
            "elapsed_ms": elapsed_ms,
            "row_limit": limits.row_limit,
            "rows_returned": returned,
            "truncated": truncated,
        },
        results=rows,
        validation_notes=notes,
        recommended_next_steps=next_steps,
        status="ok",
    )
