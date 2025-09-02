"""nl2sql-mcp package for natural language to SQL conversion.

Provides Model Context Protocol server for converting natural language
queries into SQL statements with intelligent database schema analysis.
"""

from .builders import (
    DatabaseSummaryBuilder,
    QuerySchemaResultBuilder,
    TableInfoBuilder,
)
from .models import (
    ColumnDetail,
    DatabaseSummary,
    JoinExample,
    QuerySchemaResult,
    SubjectAreaData,
    TableInfo,
    TableSummary,
)
from .services import ConfigService, SchemaService

__all__ = [  # noqa: RUF022
    # Builders
    "DatabaseSummaryBuilder",
    "QuerySchemaResultBuilder",
    "TableInfoBuilder",
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
