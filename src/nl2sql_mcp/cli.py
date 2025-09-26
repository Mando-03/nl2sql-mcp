"""Command-line entrypoint for the nl2sql-mcp FastMCP server.

This module exposes the package's CLI via the FastMCP-provided `app` object.
If invoked without any command-line arguments, it defaults to executing the
`run` subcommand for a streamlined developer experience (equivalent to running
`nl2sql-mcp run`).
"""

from __future__ import annotations

import traceback

from fastmcp.utilities.logging import get_logger

from nl2sql_mcp.server import mcp

# Configure a module-level logger for local server logs.
_logger = get_logger(__name__)


def main() -> None:
    """Start the nl2sql-mcp FastMCP server via CLI."""
    mcp.run()
    try:
        mcp.run()
    except KeyboardInterrupt:
        _logger.info("Interrupted by user. Exiting cleanly.")
    except Exception:  # noqa: BLE001
        traceback.print_exc(limit=1)


if __name__ == "__main__":
    # Delegate to main() so behavior is consistent across execution paths.
    main()
