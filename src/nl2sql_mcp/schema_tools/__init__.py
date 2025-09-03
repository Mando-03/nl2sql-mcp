"""Intelligence module for nl2sql-mcp.

Provides database schema analysis and semantic search capabilities for
natural language to SQL generation. This module includes comprehensive
database schema exploration, semantic profiling, and query-driven table
retrieval functionality.

Main Components:
- SchemaExplorer: Primary orchestrator class for schema analysis
- QueryEngine: Query processor for schema cards and SQL generation
- Data Models: ColumnProfile, TableProfile, SchemaCard for metadata storage
- Constants & Enums: Configuration and classification enums
- Exceptions: Structured error handling for different failure modes

Example Usage:
    >>> import sqlalchemy as sa
    >>> from nl2sql_mcp.schema_tools import SchemaExplorer, QueryEngine, SchemaExplorerConfig
    >>>
    >>> # Stage 1: Build schema card (run once, expensive)
    >>> engine = sa.create_engine("postgresql://user:pass@host/db")
    >>> config = SchemaExplorerConfig()
    >>> explorer = SchemaExplorer(engine, config)
    >>> schema_card = explorer.build_index()
    >>>
    >>> # Stage 2: Process queries (fast, sub-second)
    >>> query_engine = QueryEngine(schema_card, config)
    >>> # QueryEngine provides retrieval and expansion capabilities for MCP server
"""

# Import main exports from the refactored modules
from .constants import ColumnRole, RetrievalApproach, TableArchetype
from .exceptions import (
    EmbeddingError,
    ReflectionError,
    SamplingError,
    SchemaExplorerError,
)
from .explorer import SchemaExplorer
from .models import ColumnProfile, SchemaCard, SchemaExplorerConfig, TableProfile
from .query_engine import QueryEngine

__all__ = [
    # Data models
    "ColumnProfile",
    "ColumnRole",
    "EmbeddingError",
    "QueryEngine",
    "ReflectionError",
    "RetrievalApproach",
    "SamplingError",
    "SchemaCard",
    "SchemaExplorer",
    "SchemaExplorerConfig",
    "SchemaExplorerError",
    "TableArchetype",
    "TableProfile",
]
