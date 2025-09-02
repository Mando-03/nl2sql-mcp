"""SQLGlot MCP tools harness.

Demonstrates the sqlglot-backed helpers exposed by the MCP server package:
 - sql_validate               → Pre-execution syntax check and normalization
 - sql_transpile_to_database  → Source dialect → active DB dialect
 - sql_optimize_for_database  → Pretty/normalize; optional schema-aware optimize
 - sql_extract_metadata       → AST-driven tables/columns/joins/aggregations
 - sql_assist_from_error      → Post-error suggestions and likely causes

The harness automatically detects the database dialect from SQLAlchemy using
the NL2SQL_MCP_DATABASE_URL environment variable and maps it to a sqlglot
dialect. It then runs several examples and prints concise, LLM-oriented output.

Usage:
    uv run python scripts/test_sqlglot_harness.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Final

import dotenv

# Load env early
dotenv.load_dotenv()

# Add the project src/ to Python path for local imports when run directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

import sqlalchemy as sa  # noqa: E402

from nl2sql_mcp.services.config_service import ConfigService  # noqa: E402
from nl2sql_mcp.sqlglot_tools import (  # noqa: E402
    SqlglotService,
    map_sqlalchemy_to_sqlglot,
)
from nl2sql_mcp.sqlglot_tools.models import (  # noqa: E402
    Dialect,
    SqlErrorAssistRequest,
    SqlMetadataRequest,
    SqlOptimizeRequest,
    SqlTranspileRequest,
    SqlValidationRequest,
)

SEPARATOR: Final[str] = "=" * 72


def banner(title: str) -> None:
    print(f"\n{SEPARATOR}\n{title}\n{SEPARATOR}")


def section(title: str) -> None:
    print(f"\n-- {title}")


def detect_active_dialect() -> Dialect:
    """Detect the active database dialect via SQLAlchemy and map to sqlglot dialect.

    Raises:
        ValueError: when NL2SQL_MCP_DATABASE_URL is not set
    """
    url = ConfigService.get_database_url()
    engine = sa.create_engine(url)
    try:
        sa_name = engine.dialect.name  # e.g., 'postgresql'
    finally:
        engine.dispose()
    return map_sqlalchemy_to_sqlglot(sa_name)


def demonstrate_validate(svc: SqlglotService, dialect: Dialect) -> None:
    section("Validate and normalize SQL")
    samples = [
        "select 1",
        "selec 1",  # intentionally invalid
    ]
    for sql in samples:
        res = svc.validate(SqlValidationRequest(sql=sql, dialect=dialect))
        status = "VALID" if res.is_valid else "INVALID"
        print(f"> {status}: {sql}")
        if res.error_message:
            print(f"  error: {res.error_message}")
        if res.normalized_sql:
            print(f"  normalized: {res.normalized_sql}")


def demonstrate_transpile(svc: SqlglotService, target: Dialect) -> None:
    section("Transpile to active database dialect")
    if target == "tsql":
        source_sql = "SELECT name FROM users ORDER BY name LIMIT 5"
        res = svc.transpile(
            SqlTranspileRequest(
                sql=source_sql, source_dialect="postgres", target_dialect=target, pretty=True
            )
        )
        print("> source (postgres):", source_sql)
        print(f"> target ({target}):", res.sql)
    else:
        source_sql = "SELECT TOP 5 name FROM dbo.Users ORDER BY name"
        res = svc.transpile(
            SqlTranspileRequest(
                sql=source_sql, source_dialect="tsql", target_dialect=target, pretty=True
            )
        )
        print("> source (tsql):", source_sql)
        print(f"> target ({target}):", res.sql)
    if res.warnings:
        print("  warnings:", "; ".join(res.warnings))


def demonstrate_optimize(svc: SqlglotService, dialect: Dialect) -> None:
    section("Optimize/normalize for database dialect")
    sql = "SELECT  o.customer_id, SUM(o.amount) amt FROM orders o GROUP BY o.customer_id"
    res_basic = svc.optimize(SqlOptimizeRequest(sql=sql, dialect=dialect, schema_map=None))
    print("> basic:")
    print("  ", res_basic.sql)

    # Provide a tiny schema map to show the interface; optimizer may or may not
    # materially change output depending on rules and version.
    schema_map = {"orders": {"customer_id": "int", "amount": "decimal"}}
    res_schema = svc.optimize(SqlOptimizeRequest(sql=sql, dialect=dialect, schema_map=schema_map))
    print("> schema-aware:")
    print("  ", res_schema.sql)


def demonstrate_metadata(svc: SqlglotService, dialect: Dialect) -> None:
    section("Extract query metadata")
    sql = (
        "SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON o.customer_id=c.id "
        "WHERE o.created_at >= DATE '2024-01-01' GROUP BY c.name ORDER BY 2 DESC"
    )
    meta = svc.metadata(SqlMetadataRequest(sql=sql, dialect=dialect))
    print("> query type:", meta.query_type)
    print("> tables:", ", ".join(meta.tables) or "-")
    print("> columns:", ", ".join(meta.columns) or "-")
    print(
        "> flags:",
        f"joins={meta.has_joins} subqueries={meta.has_subqueries} aggs={meta.has_aggregations}",
    )


def demonstrate_error_assist(svc: SqlglotService, dialect: Dialect) -> None:
    section("Assist from execution error")
    if dialect == "tsql":
        sql = "SELECT * FROM orders LIMIT 3"
        error = "Incorrect syntax near 'LIMIT'."
    else:
        sql = "SELECT TOP 3 * FROM orders"
        error = 'syntax error at or near "TOP"'
    helpres = svc.assist_error(
        SqlErrorAssistRequest(sql=sql, error_message=error, dialect=dialect)
    )
    print("> normalized:")
    print("  ", helpres.normalized_sql or "(parse failed)")
    if helpres.likely_causes:
        print("> likely causes:")
        for c in helpres.likely_causes:
            print("  •", c)
    if helpres.suggested_fixes:
        print("> suggested fixes:")
        for f in helpres.suggested_fixes:
            print("  •", f)


def main() -> None:
    banner("SQLGlot MCP Tools Demonstration")
    parser = argparse.ArgumentParser(description="Demo sqlglot helpers")
    parser.add_argument(
        "--target-dialect",
        dest="target",
        choices=[
            "sql",
            "postgres",
            "mysql",
            "sqlite",
            "tsql",
            "oracle",
            "snowflake",
            "bigquery",
        ],
        help="Override detected target dialect",
    )
    args = parser.parse_args()

    if args.target:
        dialect = args.target  # type: ignore[assignment]
    else:
        try:
            dialect = detect_active_dialect()
        except ValueError as e:
            print(f"❌ {e}")
            print("Set NL2SQL_MCP_DATABASE_URL or use --target-dialect.")
            sys.exit(1)

    print(f"Active database dialect (sqlglot): {dialect}")
    svc = SqlglotService(default_dialect=dialect)

    demonstrate_validate(svc, dialect)
    demonstrate_transpile(svc, dialect)
    demonstrate_optimize(svc, dialect)
    demonstrate_metadata(svc, dialect)
    demonstrate_error_assist(svc, dialect)

    section("Complete")
    print("✅ SQLGlot helpers exercised successfully.")


if __name__ == "__main__":
    main()
