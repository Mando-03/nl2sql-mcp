# Repository Guidelines

## Project Structure & Modules
- `src/nl2sql_mcp/`: Main package (server, intelligence, services, builders).
- `scripts/`: Local utilities (e.g., `test_intelligence_harness.py`).
- `tests/`: Test suite placeholder; add `test_*.py` files here.
- `docs/`, `examples/`, `data/`: Reference materials and sample assets.
- Config: `pyproject.toml` (uv, ruff, pytest, basedpyright), `.env`/`.env.example`.

## Setup, Build & Run
- Install deps: `uv sync`
- Lint: `uv run ruff check .` (format: `uv run ruff format .`)
- Type check: `uv run basedpyright`
- Tests: `uv run pytest -q`
- Run MCP server: `uv run nl2sql-mcp` (entrypoint) or `uv run python -m nl2sql_mcp.server`
- Optional: set `NL2SQL_MCP_DEBUG_TOOLS=1` to also expose `find_tables` and `find_columns`.

## Coding Style & Naming
- Python 3.13, spaces, max line length 99, double quotes.
- Type hints required; strict type checking via basedpyright.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Keep imports sorted; follow ruff rules configured in `pyproject.toml`.

## Testing Guidelines
- Framework: pytest (strict config/markers enabled).
- Place tests in `tests/`, files `test_*.py`, functions `test_*`.
- Run fast tests locally: `uv run pytest -q`.
- For schema-dependent checks, prefer the harness or ephemeral DBs; avoid external side effects.

## Commit & Pull Request Guidelines
- Commits: use Conventional Commits where practical (e.g., `feat:`, `fix:`, `chore:`).
- PRs must include: clear description, rationale, before/after notes, linked issues, and test coverage or harness output when applicable.
- CI expectations: lint (`ruff`), type check (`basedpyright`), and tests must pass.

## Security & Configuration
- Required env: `NL2SQL_MCP_DATABASE_URL` (see `.env.example`). Do not commit secrets; use `.env` locally.
- Drivers/engines: SQLAlchemy with adapters (e.g., `pyodbc` for SQL Server); ensure drivers are installed on your system.

## Architecture Notes
- Entry point `nl2sql_mcp.server:main` exposes a FastMCP server with intent-first tools for planning and execution. Intelligence components live under `src/nl2sql_mcp/schema_tools` and are exercised by the harness script.
- **Never** hard code any schema-specific logic or hardcoded values in the codebase. This MCP should be designed to be flexible and adaptable to different schemas and environments.

## Essential MCP Tools (LLM-first)

- `get_init_status()` — Report server readiness and initialization progress.
- `get_database_overview(req: DatabaseOverviewRequest)` — Summarize schemas and key areas to orient planning.
- `plan_query_for_intent(req: PlanQueryRequest)` — Plan a SQL solution for a natural-language request; returns minimal schema context, join plan, clarifications, confidence, and a `draft_sql`.
- `get_table_info(req: TableInfoRequest)` — Explain a table's purpose, columns, relationships, and representative values.
- `execute_query(req: ExecuteQueryRequest)` — Execute a SELECT safely with automatic validation and dialect handling; returns typed results with `next_action` and `assist_notes` on errors.

Optional (debug): `find_tables(FindTablesRequest)`, `find_columns(FindColumnsRequest)` when `NL2SQL_MCP_DEBUG_TOOLS=1`.

### Typical Workflow

1. `get_init_status` → proceed when READY.
2. `get_database_overview` to orient.
3. `plan_query_for_intent` with the user's request; if `clarifications` present, ask the user; if `draft_sql` present, continue.
4. Optionally `get_table_info` for key tables.
5. `execute_query` with `draft_sql` or refined SQL; follow `next_action` and `assist_notes`.

### Usage Examples

Inputs below show the request model JSON payloads passed to each tool.

- PlanQueryRequest
  - Example:
    ```json
    {
      "request": "Total revenue by month for 2024 in the US",
      "constraints": {
        "time_range": "2024-01-01..2024-12-31",
        "region": "US",
        "metric": "revenue"
      },
      "detail_level": "standard",
      "budget": {"tables": 5, "columns_per_table": 20, "sample_values": 3}
    }
    ```

- DatabaseOverviewRequest
  - Example:
    ```json
    {"include_subject_areas": true, "area_limit": 8}
    ```

- TableInfoRequest
  - Example:
    ```json
    {
      "table_key": "sales.orders",
      "include_samples": true,
      "column_role_filter": ["metric", "date"],
      "max_sample_values": 5
    }
    ```

- ExecuteQueryRequest
  - Example:
    ```json
    {
      "sql": "SELECT c.customer_id, SUM(o.amount) AS revenue\nFROM sales.orders o\nJOIN sales.customers c ON c.id = o.customer_id\nWHERE o.order_date >= DATE '2024-01-01' AND o.order_date < DATE '2025-01-01'\nGROUP BY c.customer_id\nORDER BY revenue DESC\nLIMIT 50"
    }
    ```

- FindTablesRequest (debug only)
  - Example:
    ```json
    {"query": "customer orders", "limit": 10, "approach": "combo", "alpha": 0.7}
    ```

- FindColumnsRequest (debug only)
  - Example:
    ```json
    {"keyword": "email", "limit": 25, "by_table": "crm.customers"}
    ```

## Documentation
- FastMCP documentation: [gofastmcp.com](https://gofastmcp.com/llms.txt)
