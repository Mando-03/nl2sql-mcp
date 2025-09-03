"""FastMCP server implementation for nl2sql-mcp."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import contextlib
from contextlib import asynccontextmanager
import logging

import dotenv
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

from nl2sql_mcp.execute.mcp_tools import register_execute_query_tool
from nl2sql_mcp.schema_tools.mcp_tools import register_intelligence_tools
from nl2sql_mcp.services.config_service import ConfigService
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager
from nl2sql_mcp.sqlglot_tools import SqlglotService

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
register_intelligence_tools(mcp)
register_execute_query_tool(mcp, sqlglot_service=_sqlglot_service)


def main() -> None:
    """Run the MCP server."""
    try:
        # Fail fast if required environment variables are missing
        try:
            # Validate database configuration early; LLM config no longer required
            ConfigService.get_database_url()
        except ValueError:
            _logger.exception("Startup configuration error")
            raise SystemExit(1) from None

        with contextlib.suppress(KeyboardInterrupt):
            mcp.run()
    except (RuntimeError, OSError):
        logging.getLogger(__name__).exception("Exception in server startup")
        raise


if __name__ == "__main__":
    main()
