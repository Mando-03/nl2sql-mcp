"""FastMCP server implementation for nl2sql-mcp."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import dotenv
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from starlette.requests import Request
from starlette.responses import JSONResponse

from nl2sql_mcp.execute.mcp_tools import register_execute_query_tool
from nl2sql_mcp.schema_tools.mcp_tools import register_intelligence_tools
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager
from nl2sql_mcp.sqlglot_tools import SqlglotService

# Load environment variables
dotenv.load_dotenv()

# Configure a module-level logger for local server logs.
_logger = get_logger(__name__)


# -- Context Manager for SchemaService initialization -------------------
@asynccontextmanager
async def lifespan(_mcp_instance: FastMCP) -> AsyncGenerator[None]:
    """FastMCP lifespan context manager for schema service initialization."""
    manager = SchemaServiceManager.get_instance()
    try:
        _logger.info("Starting SchemaService initialization in background during lifespan startup")
        manager.start_background_initialization()
        yield
    except Exception:
        _logger.exception("Error during SchemaService initialization")
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
sqlglot_service = SqlglotService()

register_intelligence_tools(mcp)
register_execute_query_tool(mcp, sqlglot_service=sqlglot_service)


# -- Health Check ----------------------------------------------------------
@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "mcp-server"})


# -- Main Entrypoint -------------------------------------------------------

# Use fastmcp command to start the server
# fastmcp run
