"""Sqlglot service layer providing typed, pure operations.

All methods are side-effect-free and designed for unit testing.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
import logging

import sqlglot
from sqlglot import expressions as sgl_exp

from .models import (
    Dialect,
    SqlErrorAssistRequest,
    SqlErrorAssistResult,
    SqlMetadataRequest,
    SqlMetadataResult,
    SqlOptimizeRequest,
    SqlOptimizeResult,
    SqlTranspileRequest,
    SqlTranspileResult,
    SqlValidationRequest,
    SqlValidationResult,
)

SQLALCHEMY_TO_SQLGLOT: dict[str, Dialect] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "mssql": "tsql",
    "sqlserver": "tsql",
    "oracle": "oracle",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
}


def map_sqlalchemy_to_sqlglot(sa_dialect_name: str) -> Dialect:
    """Map a SQLAlchemy dialect name to a sqlglot dialect literal.

    Falls back to generic "sql" when unknown.
    """
    return SQLALCHEMY_TO_SQLGLOT.get(sa_dialect_name.lower(), "sql")


@lru_cache(maxsize=256)
def _cached_parse(sql: str, dialect: Dialect) -> sqlglot.Expression | None:
    """Small cache for parse results to speed up repetitive calls."""
    return sqlglot.parse_one(sql, dialect=dialect)


class SqlglotService:
    """Typed wrapper around sqlglot functionality.

    Methods avoid raising on common user errors and instead return
    structured results suitable for LLM consumption.
    """

    def __init__(
        self, default_dialect: Dialect = "sql", logger: logging.Logger | None = None
    ) -> None:
        self.default_dialect = default_dialect
        self._logger = logger or logging.getLogger(__name__)

    # ---- validation -----------------------------------------------------
    def validate(self, req: SqlValidationRequest) -> SqlValidationResult:
        """Parse and validate SQL, returning pretty SQL on success."""
        try:
            parsed = _cached_parse(req.sql, req.dialect)
            if parsed is None:
                return SqlValidationResult(
                    is_valid=False,
                    error_message="Failed to parse SQL query",
                    normalized_sql=None,
                    target_dialect=req.dialect,
                )
            return SqlValidationResult(
                is_valid=True,
                error_message=None,
                normalized_sql=parsed.sql(dialect=req.dialect, pretty=True),
                target_dialect=req.dialect,
            )
        except Exception as e:  # noqa: BLE001 - returning typed error
            return SqlValidationResult(
                is_valid=False,
                error_message=f"SQL parsing error: {e}",
                normalized_sql=None,
                target_dialect=req.dialect,
            )

    # ---- transpile ------------------------------------------------------
    def transpile(self, req: SqlTranspileRequest) -> SqlTranspileResult:
        """Transpile SQL from one dialect to another using sqlglot."""
        warnings: list[str] = []
        try:
            out = sqlglot.transpile(
                req.sql,
                read=req.source_dialect,
                write=req.target_dialect,
                pretty=req.pretty,
            )
            if not out:
                warnings.append(
                    "Transpilation returned empty result; falling back to original SQL"
                )
                return SqlTranspileResult(
                    sql=req.sql, warnings=warnings, target_dialect=req.target_dialect
                )
            return SqlTranspileResult(
                sql=out[0], warnings=warnings, target_dialect=req.target_dialect
            )
        except Exception as e:  # noqa: BLE001 - return typed failure info
            self._logger.warning("Transpile failed: %s", e)
            warnings.append(f"Transpile failed: {e}")
            return SqlTranspileResult(
                sql=req.sql, warnings=warnings, target_dialect=req.target_dialect
            )

    # ---- optimize -------------------------------------------------------
    def optimize(self, req: SqlOptimizeRequest) -> SqlOptimizeResult:
        """Apply sqlglot optimizer; use schema map when provided."""
        applied: list[str] = []
        notes: list[str] = []
        try:
            parsed = _cached_parse(req.sql, req.dialect)
            if parsed is None:
                return SqlOptimizeResult(
                    sql=req.sql,
                    applied_rules=applied,
                    notes=["Parse failed"],
                    target_dialect=req.dialect,
                )

            if req.schema_map:
                # Lazy import to avoid type-checker partial stubs at module import time
                from sqlglot.optimizer import (  # noqa: PLC0415
                    optimize as sgl_optimize,  # pyright: ignore[reportUnknownVariableType]
                )

                optimized = sgl_optimize(parsed, schema=req.schema_map)
                applied.append("schema-aware-optimizer")
                return SqlOptimizeResult(
                    sql=optimized.sql(dialect=req.dialect, pretty=True),
                    applied_rules=applied,
                    notes=notes,
                    target_dialect=req.dialect,
                )
            # Basic pretty/normalize when no schema map
            return SqlOptimizeResult(
                sql=parsed.sql(dialect=req.dialect, pretty=True),
                applied_rules=applied,
                notes=notes,
                target_dialect=req.dialect,
            )
        except Exception as e:  # noqa: BLE001 - return typed failure info
            self._logger.warning("Optimize failed: %s", e)
            notes.append(f"Optimize failed: {e}")
            return SqlOptimizeResult(
                sql=req.sql, applied_rules=applied, notes=notes, target_dialect=req.dialect
            )

    # ---- metadata -------------------------------------------------------
    def metadata(self, req: SqlMetadataRequest) -> SqlMetadataResult:
        """Extract structural metadata from the SQL AST."""
        try:
            parsed = _cached_parse(req.sql, req.dialect)
            if parsed is None:
                return SqlMetadataResult(
                    query_type="Unknown",
                    tables=[],
                    columns=[],
                    functions=[],
                    has_joins=False,
                    has_subqueries=False,
                    has_aggregations=False,
                    target_dialect=req.dialect,
                )

            tables: list[str] = []
            columns: list[str] = []
            functions: list[str] = []

            tables = [t.name for t in parsed.find_all(sgl_exp.Table) if t.name]
            columns = [c.name for c in parsed.find_all(sgl_exp.Column) if c.name]
            for f in parsed.find_all(sgl_exp.Func):
                # Prefer declared function name when available; otherwise use class name
                raw_name = getattr(f, "name", None)
                name = raw_name if isinstance(raw_name, str) and raw_name else type(f).__name__
                functions.append(name)

            # Robust aggregation detection: check for known aggregate names or GROUP BY clause
            agg_funcs: set[str] = {"COUNT", "SUM", "AVG", "MIN", "MAX", "GROUP_CONCAT"}
            has_agg_funcs = any(fn.upper() in agg_funcs for fn in functions)
            has_group_by = bool(parsed.args.get("group"))
            has_aggs = has_agg_funcs or has_group_by

            return SqlMetadataResult(
                query_type=type(parsed).__name__,
                tables=tables,
                columns=columns,
                functions=functions,
                has_joins=bool(list(parsed.find_all(sgl_exp.Join))),
                has_subqueries=bool(list(parsed.find_all(sgl_exp.Subquery))),
                has_aggregations=has_aggs,
                target_dialect=req.dialect,
            )
        except Exception as e:  # noqa: BLE001 - degrade gracefully
            self._logger.warning("Metadata extraction failed: %s", e)
            return SqlMetadataResult(
                query_type="Unknown",
                tables=[],
                columns=[],
                functions=[],
                has_joins=False,
                has_subqueries=False,
                has_aggregations=False,
                target_dialect=req.dialect,
            )

    # ---- error assist ---------------------------------------------------
    def assist_error(self, req: SqlErrorAssistRequest) -> SqlErrorAssistResult:
        """Heuristic assistance for execution-time SQL errors.

        This does not execute SQL; it parses and inspects the error string
        to offer concrete next steps for an LLM.
        """
        normalized: str | None = None
        likely: list[str] = []
        fixes: list[str] = []

        # Try to normalize the SQL first.
        val = self.validate(SqlValidationRequest(sql=req.sql, dialect=req.dialect))
        if val.is_valid and val.normalized_sql is not None:
            normalized = val.normalized_sql

        emsg = req.error_message.lower()

        def add_if(cond: bool, items: Iterable[str]) -> None:  # noqa: FBT001
            if cond:
                likely.extend(items)

        # Common error pattern hints (minimal but actionable)
        add_if(
            "syntax error" in emsg or "mismatched input" in emsg,
            [
                "SQL syntax near reported token is invalid for this dialect",
            ],
        )
        add_if(
            "no such table" in emsg or "relation does not exist" in emsg,
            [
                "Referenced table name may be wrong or not in search_path",
            ],
        )
        add_if(
            "no such column" in emsg or "column does not exist" in emsg,
            [
                "A selected or filtered column is misspelled or not present",
            ],
        )
        add_if(
            "function" in emsg and "does not exist" in emsg,
            [
                "Function is unsupported or has different name/arg types in this dialect",
            ],
        )
        add_if(
            "datatype mismatch" in emsg or "invalid input syntax" in emsg,
            [
                "Type mismatch in predicate or insert values",
            ],
        )

        # Suggested small edits the LLM can attempt.
        if "top " in req.sql.lower() and req.dialect in {
            "postgres",
            "mysql",
            "sqlite",
            "bigquery",
            "snowflake",
        }:
            fixes.append("Replace T-SQL TOP with LIMIT")
        if "limit" in req.sql.lower() and req.dialect in {"tsql"}:
            fixes.append("Replace LIMIT with TOP n in SELECT clause")
        if any(fn in req.sql.lower() for fn in ["ifnull(", "isnull("]):
            fixes.append("Use COALESCE for portable null handling where supported")

        return SqlErrorAssistResult(
            normalized_sql=normalized,
            likely_causes=sorted(set(likely)),
            suggested_fixes=sorted(set(fixes)),
            target_dialect=req.dialect,
        )
