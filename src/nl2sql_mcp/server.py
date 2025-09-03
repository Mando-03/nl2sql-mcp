"""FastMCP server implementation for nl2sql-mcp."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import contextlib
from contextlib import asynccontextmanager
import logging

import dotenv
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

from nl2sql_mcp.schema_tools.mcp_tools import register_intelligence_tools
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager
from nl2sql_mcp.sqlglot_tools import (
    SqlglotService,
    map_sqlalchemy_to_sqlglot,
    register_sqlglot_tools,
)

# Load environment variables
dotenv.load_dotenv()

# Configure a module-level logger for local server logs.
_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_mcp_instance: FastMCP) -> AsyncGenerator[None]:
    """FastMCP lifespan context manager for schema service initialization."""
    manager = SchemaServiceManager.get_instance()
    try:
        _logger.info("Starting SchemaService initialization in background during lifespan startup")
        manager.start_background_initialization()
        yield
    finally:
        _logger.info("Shutting down SchemaService during lifespan shutdown")
        await manager.shutdown()


# Create the main MCP server instance with lifespan
mcp = FastMCP(
    instructions=(
        "This provides a natural language to SQL "
        "Model Context Protocol server that helps convert natural language "
        "queries into SQL statements."
    ),
    lifespan=lifespan,
)

# -- Tool Registration -------------------------------------------------------

_sqlglot_service = SqlglotService()


def _active_sqlglot_dialect() -> str:
    """Resolve the current database dialect for sqlglot tools."""
    manager = SchemaServiceManager.get_instance()
    sa_name = manager.current_sqlalchemy_dialect_name()
    if sa_name:
        return map_sqlalchemy_to_sqlglot(sa_name)
    return "sql"


register_sqlglot_tools(mcp, _sqlglot_service, _active_sqlglot_dialect)  # type: ignore[arg-type]
register_intelligence_tools(mcp)


def main() -> None:
    """Run the MCP server."""
    try:
        with contextlib.suppress(KeyboardInterrupt):
            mcp.run()
    except (RuntimeError, OSError):
        logging.getLogger(__name__).exception("Exception in server startup")
        raise


if __name__ == "__main__":
    main()
