"""Agent harness for ask_database.

Runs the end-to-end agent flow using live DB + LLM env from .env and prints a
concise, LLM-oriented summary of the outcome (intent, SQL, execution meta,
first few rows, truncation guidance).

Usage:
    uv run python scripts/test_agent_harness.py "what are the top 10 customers by revenue last 30 days"
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
from typing import Final

import dotenv

# Load env early
dotenv.load_dotenv()

# Add the project src/ to Python path for local imports when run directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from nl2sql_mcp.agent.agent import run_ask_flow  # noqa: E402
from nl2sql_mcp.agent.models import AgentDeps  # noqa: E402
from nl2sql_mcp.services.config_service import ConfigService  # noqa: E402
from nl2sql_mcp.services.schema_service import SchemaService  # noqa: E402
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager  # noqa: E402
from nl2sql_mcp.sqlglot_tools import SqlglotService, map_sqlalchemy_to_sqlglot  # noqa: E402

SEPARATOR: Final[str] = "=" * 72


def banner(title: str) -> None:
    print(f"\n{SEPARATOR}\n{title}\n{SEPARATOR}")


async def _get_schema_service(wait_timeout: float = 30.0) -> SchemaService:
    mgr = SchemaServiceManager.get_instance()
    mgr.start_background_initialization()
    ok = await mgr.ensure_ready(wait_timeout=wait_timeout)
    if not ok:
        raise RuntimeError("SchemaService initialization did not complete in time")
    return await mgr.get_schema_service()


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo ask_database agent")
    parser.add_argument(
        "question",
        nargs="?",
        default="What are the top 5 customers by total order amount in the last 30 days?",
        help="Natural language question to ask the database",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=180.0,
        help=(
            "Seconds to wait for schema initialization. Use 0 for no timeout "
            "(wait until ready). Default: 180s"
        ),
    )
    args = parser.parse_args()

    # Fail early on required envs
    _ = ConfigService.get_database_url()
    llm_cfg = ConfigService.get_llm_config()
    # Avoid HF tokenizers fork-parallelism warnings in dev harness
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    # Initialize schema service and detect dialect
    # Wait for schema indexing/sampling; larger DBs can take minutes.
    wait: float | None = None if args.wait_timeout <= 0 else args.wait_timeout
    service = asyncio.run(_get_schema_service(wait_timeout=wait or 180.0))
    mgr = SchemaServiceManager.get_instance()
    sa_name = mgr.current_sqlalchemy_dialect_name() or "sql"
    dialect = map_sqlalchemy_to_sqlglot(sa_name)
    glot = SqlglotService(default_dialect=dialect)

    # Build schema context for the question (internal knobs are hidden from callers)
    schema = service.analyze_query_schema(
        args.question,
        max_tables=5,
        include_samples=False,
        max_sample_values=0,
        detail_level="standard",
        join_limit=8,
    )

    deps = AgentDeps(
        active_dialect=dialect,
        row_limit=ConfigService.result_row_limit(),
        max_cell_chars=ConfigService.result_max_cell_chars(),
        max_payload_bytes=ConfigService.result_max_payload_bytes(),
    )

    # Execute ask_database flow
    result = run_ask_flow(
        question=args.question,
        schema=schema,
        engine=service.engine,
        glot=glot,
        deps=deps,
        llm=llm_cfg,
    )

    # Print concise summary
    banner("ask_database result")
    print("intent:", result.intent)
    if result.clarifications_needed:
        print("clarifications:")
        for q in result.clarifications_needed:
            print("  -", q)
    print("dialect:", result.execution.get("dialect"))
    print("sql:")
    print(result.sql)
    print("execution:", result.execution)
    head = result.results[: min(5, len(result.results))]
    if head:
        print("rows (up to 5):")
        cols = list(head[0].keys())
        print("  | ", " | ".join(cols))
        for r in head:
            print("  | ", " | ".join(str(r[c]) for c in cols))
    if result.recommended_next_steps:
        print("next steps:")
        for s in result.recommended_next_steps:
            print("  -", s)


if __name__ == "__main__":
    main()
