"""Builders package for nl2sql-mcp.

This package contains builder classes responsible for constructing response models
from intelligence analysis results. Builders transform raw analysis data into
structured models suitable for MCP tool responses.

Main Components:
- QuerySchemaResultBuilder: Builds QuerySchemaResult objects
- DatabaseSummaryBuilder: Builds DatabaseSummary objects
- TableInfoBuilder: Builds TableInfo objects
"""

from .response_builders import (
    DatabaseSummaryBuilder,
    QuerySchemaResultBuilder,
    TableInfoBuilder,
)

__all__ = [
    "DatabaseSummaryBuilder",
    "QuerySchemaResultBuilder",
    "TableInfoBuilder",
]
