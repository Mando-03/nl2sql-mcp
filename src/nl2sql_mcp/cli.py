"""Command-line entrypoint for the nl2sql-mcp FastMCP server.

This module exposes a ``main()`` function that starts the FastMCP server
using the default STDIO transport, suitable for MCP clients. It is wired to
the ``nl2sql-mcp`` console script via the project's ``pyproject.toml``.
"""

from __future__ import annotations

from nl2sql_mcp.server import mcp


def main() -> None:
    """Start the nl2sql-mcp FastMCP server via CLI."""
    mcp.run()
