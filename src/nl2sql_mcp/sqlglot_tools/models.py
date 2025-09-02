"""Typed Pydantic models for sqlglot MCP tools.

These models are intentionally small, focused, and LLM-friendly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Keep a pragmatic set of supported dialects commonly used in this project.
Dialect = Literal[
    "sql",
    "postgres",
    "mysql",
    "sqlite",
    "tsql",
    "oracle",
    "snowflake",
    "bigquery",
]


class SqlValidationRequest(BaseModel):
    """Request to validate SQL syntax for a dialect."""

    sql: str = Field(description="SQL string to validate")
    dialect: Dialect = Field(description="Target SQL dialect for parsing")


class SqlValidationResult(BaseModel):
    """Validation result with optional normalized SQL for readability."""

    is_valid: bool = Field(description="True when the SQL parses successfully")
    error_message: str | None = Field(default=None, description="Parse error if invalid")
    normalized_sql: str | None = Field(
        default=None, description="Pretty-printed SQL when parsing succeeds"
    )
    target_dialect: Dialect = Field(
        description="Dialect used for parsing (derived from SQLAlchemy when available)"
    )


class SqlTranspileRequest(BaseModel):
    """Request to transpile SQL between dialects."""

    sql: str = Field(description="SQL to transpile")
    source_dialect: Dialect = Field(description="Source dialect")
    target_dialect: Dialect = Field(description="Target dialect")
    pretty: bool = Field(default=True, description="Return formatted SQL")


class SqlTranspileResult(BaseModel):
    """Transpiled SQL and warnings, suitable for LLMs building queries."""

    sql: str = Field(description="Transpiled SQL text")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal issues")
    target_dialect: Dialect = Field(description="Dialect used for output")


class SqlOptimizeRequest(BaseModel):
    """Request to apply sqlglot optimizations for a dialect."""

    sql: str = Field(description="SQL to optimize")
    dialect: Dialect = Field(description="Dialect for parsing and output")
    schema_map: dict[str, dict[str, str]] | None = Field(
        default=None,
        description="Optional schema map: table -> column -> type",
    )


class SqlOptimizeResult(BaseModel):
    """Optimized SQL and metadata about applied rules."""

    sql: str = Field(description="Optimized SQL text or original on failure")
    applied_rules: list[str] = Field(
        default_factory=list, description="High-level notes on transformations"
    )
    notes: list[str] = Field(default_factory=list, description="Additional remarks or caveats")
    target_dialect: Dialect = Field(description="Dialect used for output")


class SqlMetadataRequest(BaseModel):
    """Request to extract query metadata for a dialect."""

    sql: str = Field(description="SQL to analyze")
    dialect: Dialect = Field(description="Dialect for parsing")


class SqlMetadataResult(BaseModel):
    """LLM-friendly structural metadata from SQL AST."""

    query_type: str = Field(description="Top-level SQL expression type")
    tables: list[str] = Field(default_factory=list, description="Referenced table names")
    columns: list[str] = Field(default_factory=list, description="Referenced column names")
    functions: list[str] = Field(default_factory=list, description="Functions used")
    has_joins: bool = Field(description="Whether the query contains JOINs")
    has_subqueries: bool = Field(description="Whether the query contains subqueries")
    has_aggregations: bool = Field(description="Whether the query contains aggregations")
    target_dialect: Dialect = Field(description="Dialect used for parsing")


class SqlErrorAssistRequest(BaseModel):
    """Request to assist with a database execution error."""

    sql: str = Field(description="The SQL that failed at execution time")
    error_message: str = Field(description="The database error text returned by the server")
    dialect: Dialect = Field(description="Target database dialect")


class SqlErrorAssistResult(BaseModel):
    """Actionable hints for recovering from SQL execution errors."""

    normalized_sql: str | None = Field(
        default=None, description="Parsed + pretty version to aid debugging"
    )
    likely_causes: list[str] = Field(
        default_factory=list, description="Short, concrete hypotheses for the failure"
    )
    suggested_fixes: list[str] = Field(
        default_factory=list,
        description="Small edits or strategies an LLM can apply to fix the query",
    )
    target_dialect: Dialect = Field(description="Dialect assumed for analysis")
