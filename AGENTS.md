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
- Entry point `nl2sql_mcp.server:main` exposes a FastMCP server with tools for schema discovery and query planning. Intelligence components live under `src/nl2sql_mcp/intelligence` and are exercised by the harness script.
- **Never** hard code any schema-specific logic or hardcoded values in the codebase. This MCP should be designed to be flexible and adaptable to different schemas and environments.

## Documentation
- FastMCP documentation: [gofastmcp.com](https://gofastmcp.com/llms.txt)
