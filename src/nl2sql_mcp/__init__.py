"""nl2sql-mcp package for natural language to SQL conversion.

Provides Model Context Protocol (FastMCP) server capabilities for converting
natural-language queries into SQL with intelligent database schema analysis.
"""

from nl2sql_mcp.models import (
    ColumnDetail,
    DatabaseSummary,
    JoinExample,
    QuerySchemaResult,
    SubjectAreaData,
    TableInfo,
    TableSummary,
)
from nl2sql_mcp.services import ConfigService, SchemaService

__all__ = [  # noqa: RUF022
    # Core models
    "ColumnDetail",
    "DatabaseSummary",
    "JoinExample",
    "QuerySchemaResult",
    "SubjectAreaData",
    "TableInfo",
    "TableSummary",
    # Services
    "ConfigService",
    "SchemaService",
]
