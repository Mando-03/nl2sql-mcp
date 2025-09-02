"""Pydantic models for MCP tool I/O.

Minimal, task-focused models used by the MCP server tools and builders.
Keeping surface area small avoids overengineering and simplifies maintenance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
