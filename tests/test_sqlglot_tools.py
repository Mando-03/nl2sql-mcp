from __future__ import annotations

import logging

from nl2sql_mcp.sqlglot_tools import (
    SqlglotService,
    map_sqlalchemy_to_sqlglot,
)
from nl2sql_mcp.sqlglot_tools.models import (
    SqlAutoTranspileRequest,
    SqlErrorAssistRequest,
    SqlMetadataRequest,
    SqlOptimizeRequest,
    SqlTranspileRequest,
    SqlValidationRequest,
)


def test_map_sqlalchemy_to_sqlglot_known() -> None:
    assert map_sqlalchemy_to_sqlglot("postgresql") == "postgres"
    assert map_sqlalchemy_to_sqlglot("mssql") == "tsql"
    assert map_sqlalchemy_to_sqlglot("sqlite") == "sqlite"


def test_validate_and_metadata() -> None:
    svc = SqlglotService(logger=logging.getLogger(__name__))
    sql = "select 1"
    v = svc.validate(SqlValidationRequest(sql=sql, dialect="postgres"))
    assert v.is_valid is True
    assert v.normalized_sql is not None

    meta = svc.metadata(SqlMetadataRequest(sql="SELECT 1", dialect="postgres"))
    assert meta.query_type
    assert meta.has_joins is False


def test_transpile_top_to_limit_postgres() -> None:
    svc = SqlglotService()
    t = svc.transpile(
        SqlTranspileRequest(
            sql="SELECT TOP 5 * FROM dbo.Users",
            source_dialect="tsql",
            target_dialect="postgres",
            pretty=True,
        )
    )
    assert "limit" in t.sql.lower()


def test_optimize_roundtrip() -> None:
    svc = SqlglotService()
    res = svc.optimize(
        SqlOptimizeRequest(sql="SELECT * FROM x", dialect="postgres", schema_map=None)
    )
    assert "select" in res.sql.lower()


def test_error_assist_syntax_hint() -> None:
    svc = SqlglotService()
    out = svc.assist_error(
        SqlErrorAssistRequest(
            sql="SELECT TOP 3 * FROM t",
            error_message='syntax error at or near "TOP"',
            dialect="postgres",
        )
    )
    assert any("replace" in s.lower() for s in out.suggested_fixes)


def test_detect_and_auto_transpile() -> None:
    svc = SqlglotService()
    # Use a clearly T-SQL flavored query but target postgres
    res = svc.auto_transpile_for_database(
        SqlAutoTranspileRequest(
            sql="SELECT TOP 2 name FROM dbo.Users ORDER BY name",
            target_dialect="postgres",
        )
    )
    assert res.detected_source in {"tsql", "sql"}
    assert "limit" in res.sql.lower()
