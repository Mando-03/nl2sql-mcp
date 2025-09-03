from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from nl2sql_mcp.execute.runner import (
    ExecutionLimits,
    enforce_select_only,
    run_execute_flow,
    strip_trailing_semicolon,
)
from nl2sql_mcp.sqlglot_tools import SqlglotService


def _mk_engine() -> sa.Engine:
    return sa.create_engine("sqlite+pysqlite:///:memory:")


def _setup_sqlite(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO t(name) VALUES ('Alice'),('Bob'),('Charlie')"))


def test_strip_semicolon() -> None:
    assert strip_trailing_semicolon("select 1;") == "select 1"
    assert strip_trailing_semicolon("select 1") == "select 1"


def test_enforce_select_only() -> None:
    enforce_select_only("SELECT * FROM t")  # no error
    for bad in [
        "INSERT INTO x VALUES (1)",
        "UPDATE x SET a=1",
        "DELETE FROM x",
        "CREATE TABLE x(a int)",
        "DROP TABLE x",
        "TRUNCATE TABLE x",
        "GRANT SELECT ON x TO y",
    ]:
        with pytest.raises(ValueError, match="Only SELECT"):
            enforce_select_only(bad)


def test_run_execute_flow_sqlite_basic() -> None:
    engine = _mk_engine()
    _setup_sqlite(engine)
    glot = SqlglotService()

    result = run_execute_flow(
        sql="SELECT id, name FROM t ORDER BY id",
        engine=engine,
        glot=glot,
        active_dialect="sqlite",
        limits=ExecutionLimits(row_limit=2, max_cell_chars=10),
    )

    assert result.status == "ok"
    assert result.execution["rows_returned"] == 2
    assert result.execution["truncated"] is True
    assert len(result.results) == 2
    assert {"id", "name"}.issubset(result.results[0].keys())
