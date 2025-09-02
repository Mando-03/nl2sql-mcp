"""SQLGlot-backed MCP tools package.

Provides typed service wrappers around sqlglot and MCP tool registration.
Implementation is pure and dependency-injected for easy testing.
"""

from __future__ import annotations

from .mcp_tools import register_sqlglot_tools
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
from .service import SqlglotService, map_sqlalchemy_to_sqlglot

__all__ = [
    "Dialect",
    "SqlErrorAssistRequest",
    "SqlErrorAssistResult",
    "SqlMetadataRequest",
    "SqlMetadataResult",
    "SqlOptimizeRequest",
    "SqlOptimizeResult",
    "SqlTranspileRequest",
    "SqlTranspileResult",
    "SqlValidationRequest",
    "SqlValidationResult",
    "SqlglotService",
    "map_sqlalchemy_to_sqlglot",
    "register_sqlglot_tools",
]
