"""Command-line entrypoint for the nl2sql-mcp FastMCP server.

This module exposes the package's CLI via the FastMCP-provided `app` object.
If invoked without any command-line arguments, it defaults to executing the
`run` subcommand for a streamlined developer experience (equivalent to running
`nl2sql-mcp run`).
"""

from __future__ import annotations

import sys

from fastmcp.cli.cli import app


def main() -> None:
    """Start the nl2sql-mcp FastMCP server via CLI.

    Behavior:
    - When invoked with no additional command-line arguments (i.e., only the
      program name is present in ``sys.argv``), call the FastMCP CLI with a
      default of ``run`` to start the server immediately.
    - Otherwise, defer to the arguments provided by the user.
    """
    if len(sys.argv) == 1:
        # No CLI arguments provided; default to the `run` subcommand.
        app(tokens=["run"])  # type: ignore[call-arg]
    else:
        # Use the actual command-line arguments as provided.
        app()


if __name__ == "__main__":
    # Delegate to main() so behavior is consistent across execution paths.
    main()
