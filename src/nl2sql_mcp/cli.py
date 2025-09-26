"""Command-line entrypoint for the nl2sql-mcp FastMCP server."""

from __future__ import annotations

from fastmcp.cli.cli import app


def main() -> None:
    """Start the nl2sql-mcp FastMCP server via CLI."""
    app()


if __name__ == "__main__":
    app()  # Automatically uses sys.argv
