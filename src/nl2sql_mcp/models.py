"""Pydantic models for MCP tool I/O.

Minimal, task-focused models used by the MCP server tools and builders.
Keeping surface area small avoids overengineering and simplifies maintenance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# -----------------------
# MCP Request Models
# -----------------------


class PlanQueryRequest(BaseModel):
    """Plan a SQL solution for a natural-language request."""

    request: str = Field(
        description=(
            "User's question or goal in natural language. Example: "
            "'Total revenue by month for 2024 for the US region.'"
        )
    )
    constraints: dict[str, str | int | float | bool] | None = Field(
        default=None,
        description=(
            "Optional constraints such as time window, dimensions, metrics, or filters. "
            "Example: {time_range: '2024-01-01..2024-12-31', region: 'US', metric: 'revenue'}"
        ),
    )
    detail_level: Literal["standard", "full"] = Field(
        default="standard",
        description=(
            "Controls verbosity of planning output. 'full' returns more columns and joins."
        ),
    )
    budget: dict[str, int] | None = Field(
        default=None,
        description=(
            "Optional response-size caps. Keys: tables, columns_per_table, sample_values. "
            "Example: {tables: 5, columns_per_table: 20, sample_values: 3}."
        ),
    )


class DatabaseOverviewRequest(BaseModel):
    """Get a high-level overview to orient planning."""

    include_subject_areas: bool = Field(
        default=False, description="Include structured subject area data when true"
    )
    area_limit: int = Field(
        default=8, ge=1, description="Maximum number of subject areas to include"
    )


class TableInfoRequest(BaseModel):
    """Explain a table in business and SQL terms."""

    table_key: str = Field(description="Fully qualified table name 'schema.table'")
    include_samples: bool = Field(
        default=True, description="Include representative sample values for columns"
    )
    column_role_filter: list[Literal["metric", "date", "key", "category", "text"]] | None = Field(
        default=None,
        description="If provided, only return columns with these business roles",
    )
    max_sample_values: int = Field(
        default=5, ge=0, description="Maximum samples per column when samples are included"
    )
    relationship_limit: int | None = Field(
        default=None, ge=0, description="Limit the number of relationships returned"
    )


class ExecuteQueryRequest(BaseModel):
    """Execute a SELECT safely with validation and dialect handling."""

    sql: str = Field(
        description=(
            "SQL statement to execute. SELECT-only; non-SELECT returns a structured error."
        )
    )


# Debug-only request models (gated tools)
class FindTablesRequest(BaseModel):
    query: str = Field(description="Intent/keywords to locate relevant tables")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of hits")
    approach: Literal["combo", "lexical", "emb_table", "emb_column"] = Field(
        default="combo", description="Retrieval strategy"
    )
    alpha: float = Field(default=0.7, ge=0.0, le=1.0, description="Blend weight for combo")


class FindColumnsRequest(BaseModel):
    keyword: str = Field(description="Keyword to match columns")
    limit: int = Field(default=25, ge=1, le=200, description="Maximum number of hits")
    by_table: str | None = Field(
        default=None, description="Restrict search to a specific 'schema.table'"
    )


class SubjectAreaData(BaseModel):
    """Detailed data for a specific subject area."""

    name: str = Field(description="Human-readable name of the subject area")
    tables: list[str] = Field(description="List of table identifiers in 'schema.table' format")
    summary: str = Field(description="Descriptive summary of the subject area")


class SubjectAreaItem(BaseModel):
    """Subject area record including identifier."""

    id: str = Field(description="Subject area identifier")
    name: str = Field(description="Human-readable name of the subject area")
    tables: list[str] = Field(description="List of table identifiers in 'schema.table' format")
    summary: str = Field(description="Descriptive summary of the subject area")


class ColumnDetail(BaseModel):
    """Simple column information optimized for SQL generation."""

    name: str = Field(description="Column name")
    data_type: str = Field(description="SQL data type (prominently displayed)")
    nullable: bool = Field(description="Whether NULL values are allowed")
    is_primary_key: bool = Field(description="Whether this column is part of the primary key")
    is_foreign_key: bool = Field(description="Whether this column references another table")
    business_role: str | None = Field(
        description="Business purpose (ID, date, amount, category, etc.)"
    )
    sample_values: list[str] = Field(description="Representative sample values from the data")
    constraints: list[str] = Field(description="Value constraints (enum values, ranges, patterns)")


class JoinExample(BaseModel):
    """Clear JOIN example with actual SQL syntax."""

    from_table: str = Field(description="Source table name")
    to_table: str = Field(description="Target table name")
    sql_syntax: str = Field(description="Complete JOIN clause with ON condition")
    relationship_type: str = Field(description="Type of relationship (1:1, 1:many, many:many)")
    business_purpose: str = Field(description="Why these tables are typically joined together")


class JoinOnPair(BaseModel):
    """Explicit ON clause column pair used in a join plan."""

    left: str = Field(description="Left fully-qualified column 'schema.table.column'")
    right: str = Field(description="Right fully-qualified column 'schema.table.column'")


class JoinPlanStep(BaseModel):
    """Structured join plan step for deterministic SQL assembly."""

    from_table: str = Field(description="Source table name 'schema.table'")
    to_table: str = Field(description="Target table name 'schema.table'")
    on: list[JoinOnPair] = Field(description="List of ON clause column pairs")
    relationship_type: str = Field(description="Type of relationship (1:1, 1:many, many:many)")
    purpose: str = Field(description="Business purpose for this join")


class TableSummary(BaseModel):
    """Simple table information focused on SQL generation needs."""

    name: str = Field(description="Table name")
    business_purpose: str = Field(description="Clear explanation of what this table represents")
    columns: list[ColumnDetail] = Field(description="Column details with types and samples")
    primary_keys: list[str] = Field(description="Primary key column names")
    common_filters: list[str] = Field(description="Commonly used WHERE clause conditions")


class QuerySchemaResult(BaseModel):
    """Schema information optimized for answering a specific query."""

    query: str = Field(description="The natural language query being analyzed")
    relevant_tables: list[TableSummary] = Field(description="Tables needed to answer the query")
    join_examples: list[JoinExample] = Field(
        description="How to join the relevant tables (human-friendly)"
    )
    suggested_approach: str = Field(
        description="Recommended approach for writing the SQL (narrative)"
    )
    key_columns: dict[str, list[str]] = Field(
        description="Important columns by table for this query"
    )
    # New structured guidance fields for deterministic planning
    main_table: str | None = Field(
        default=None, description="Likely main/fact table to anchor the query"
    )
    join_plan: list[JoinPlanStep] = Field(
        default_factory=list, description="Structured join steps"
    )
    group_by_candidates: list[str] = Field(
        default_factory=list, description="Candidate columns to GROUP BY"
    )
    filter_candidates: list[FilterCandidate] = Field(
        default_factory=list,
        description="Suggested filters",
    )
    selected_columns: list[SelectedColumn] = Field(
        default_factory=list,
        description="Optional suggested select list",
    )
    # LLM-first planning outputs
    draft_sql: str | None = Field(
        default=None,
        description="Optional draft SELECT statement assembled from the plan",
    )
    next_action: (
        Literal[
            "execute_query",
            "request_clarification",
            "inspect_table",
            "refine_plan",
        ]
        | None
    ) = Field(
        default=None,
        description="Suggested next step based on confidence and ambiguities",
    )
    clarifications: list[str] = Field(
        default_factory=list,
        description="Concrete questions to resolve ambiguities before execution",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions the planner made that the agent may confirm",
    )
    confidence: float | None = Field(
        default=None,
        description="Heuristic confidence 0..1 that the plan matches the request",
    )
    status: Literal["ok", "needs_input", "error"] = Field(
        default="ok", description="Whether planning is ready, needs input, or failed"
    )


class DatabaseSummary(BaseModel):
    """High-level database overview for SQL context."""

    database_type: str = Field(description="Database dialect (PostgreSQL, MySQL, etc.)")
    total_tables: int = Field(description="Total number of tables")
    schemas: list[str] = Field(description="Schema names in the database")
    # Preserve compact map for quick reading
    key_subject_areas: dict[str, str] = Field(
        description="Major business areas and their purpose (compact)"
    )
    # Provide full structured subject area data when requested
    subject_areas: dict[str, SubjectAreaData] | None = Field(
        default=None, description="Structured subject areas keyed by ID"
    )
    most_important_tables: list[str] = Field(description="Tables that are frequently joined to")
    common_patterns: list[str] = Field(description="Common query patterns in this database")


class TableInfo(BaseModel):
    """Comprehensive table details for SQL development."""

    table_name: str = Field(description="Full table name with schema")
    business_description: str = Field(description="What this table represents in business terms")
    columns: list[ColumnDetail] = Field(description="All column details with types and samples")
    relationships: list[JoinExample] = Field(description="How this table connects to others")
    typical_queries: list[str] = Field(description="Common query patterns using this table")
    indexing_notes: list[str] = Field(description="Important notes about performance and indexing")
    pk_columns: list[str] = Field(default_factory=list, description="Primary key column names")
    foreign_keys: list[ForeignKeyRef] = Field(
        default_factory=list, description="Foreign key references"
    )
    approx_rowcount: int | None = Field(default=None, description="Estimated total rows if known")


class TableSearchHit(BaseModel):
    """Search hit for table discovery."""

    table: str = Field(description="Table key 'schema.table'")
    score: float = Field(description="Relevance score (normalized where applicable)")
    summary: str | None = Field(default=None, description="Short business summary if available")


class ColumnSearchHit(BaseModel):
    """Search hit for column discovery."""

    table: str = Field(description="Table key 'schema.table'")
    column: str = Field(description="Column name")
    role: str | None = Field(default=None, description="Business role if known")
    data_type: str | None = Field(default=None, description="Column SQL type if known")


class FilterCandidate(BaseModel):
    """A suggested filter operation for a column."""

    table: str
    column: str
    operator_examples: list[str]


class SelectedColumn(BaseModel):
    """A suggested select-list column with rationale."""

    table: str
    column: str
    reason: str


class ForeignKeyRef(BaseModel):
    """Foreign key reference descriptor."""

    column: str
    ref_table: str
    ref_column: str


class InitStatus(BaseModel):
    """Initialization status for schema service readiness."""

    phase: Literal["IDLE", "STARTING", "RUNNING", "READY", "FAILED", "STOPPED"]
    attempts: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str | None = None
    # Minimal descriptive text to help LLMs reason about progression
    description: str | None = Field(default=None, description="Short status description")
