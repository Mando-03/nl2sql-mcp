% NL2SQL MCP

A natural‑language‑to‑SQL Model Context Protocol (MCP) server that executes one safe, executable `SELECT` and returns concise, typed results. Built for type‑safety, testability, and cross‑database compatibility.

- Server: FastMCP tools for schema discovery, SQL assistance, and query planning
- Tool: `execute_query`—executes exactly one caller‑provided `SELECT` with strong safeguards
- Engines: Works with SQLAlchemy; validated/transpiled via `sqlglot`


## Features

- **LLM‑ready schema intelligence:** Reflects your DB, profiles columns, builds FK graphs, discovers subject areas, and returns typed planning aids.
- **Safe SQL execution:** Enforces `SELECT`‑only, normalizes dialect, validates with `sqlglot`, applies row budgets and per‑cell truncation.
- **Typed MCP tools:** Analyze query schema, search tables/columns, extract constraints, and expose SQL helpers (validate/transpile/optimize/metadata).
- **Configurable & testable:** Dependency‑injected services with Pydantic models; pure, side‑effect‑free core APIs.


## Architecture

```mermaid
graph TD
  A[Client / LLM<br/>MCP Tool Calls] -- FastMCP --> B[nl2sql-mcp Server]

  subgraph B1[Server Core]
    B11[Lifecycle / Config<br/>(Pydantic models)]
    B12[SchemaService<br/>(reflect + cache + readiness)]
    B13[Tool Router<br/>(FastMCP)]
  end

  B --> B1
  B1 -->|ready?| B12

  subgraph T[Exposed MCP Tools]
    T1[get_init_status]
    T2[get_database_overview]
    T3[plan_query_for_intent]
    T4[get_table_info]
    T5[(optional) find_tables / find_columns]
    T6[sqlglot_* helpers]
    T7[execute_query]
  end

  B13 --> T1
  B13 --> T2
  B13 --> T3
  B13 --> T4
  B13 --> T5
  B13 --> T6
  B13 --> T7

  subgraph INT[Intelligence Modules]
    I1[Schema Tools<br/>analysis + planning]
    I2[SQLGlot Tools<br/>validate / transpile / optimize / metadata]
  end

  T2 --> I1
  T3 --> I1
  T4 --> I1
  T5 --> I1
  T6 --> I2

  subgraph DB[Database]
    D1[(SQLAlchemy Engine)]
    D2[(Your RDBMS: Postgres / MySQL / SQL Server / SQLite / etc.)]
  end

  T7 -- SELECT‑only --> D1 --> D2

  I1 -->|introspection| D1
  B12 -->|reflect / cache| D1
```

Alt text: The client calls FastMCP tools exposed by the nl2sql-mcp server. A core layer manages config, readiness, and routing to tools. Intelligence modules power schema analysis and SQLGlot helpers. All database access goes through SQLAlchemy; execute_query enforces SELECT-only. The SchemaService reflects and caches metadata and reports readiness.


## Modules

- `src/nl2sql_mcp/execute/` — direct execution tool (execute_query)
- `src/nl2sql_mcp/schema_tools/` — schema intelligence MCP tools (see module README)
- `src/nl2sql_mcp/services/` — configuration, schema service, and lifecycle manager
- `src/nl2sql_mcp/sqlglot_tools/` — SQL validation/transpile/metadata MCP tools

For deeper detail, see:

- `src/nl2sql_mcp/execute/` (module docs inline)
- `src/nl2sql_mcp/schema_tools/README.md`
- `src/nl2sql_mcp/services/README.md`
- `src/nl2sql_mcp/sqlglot_tools/README.md`


## MCP Tools Overview

Schema tools (selected):
- `analyze_query_schema(query, max_tables=5, ...)` → `QuerySchemaResult` with relevant tables, join plan, key columns, group/filter candidates.
- `get_database_overview()` → `DatabaseOverview` with subject areas and summaries.
- `get_table_info(table_key, include_samples=True, ...)` → `TableInfo` with columns, PK/FK, constraints, and samples.
- `find_tables(query, limit=10, approach="combo", alpha=0.7)` → `TableSearchHit[]`.
- `find_columns(keyword, limit=25, by_table=None)` → `ColumnSearchHit[]`.
- `get_init_status()` → readiness/error details for the schema service.

SQLGlot tools:
- `sql_validate(sql)`
- `sql_transpile_to_database(sql, source_dialect)`
- `sql_auto_transpile_for_database(sql)`
- `sql_optimize_for_database(sql, schema_map?)`
- `sql_extract_metadata(sql)`
- `sql_assist_from_error(sql, error_message)`


## Tool: execute_query

Executes exactly one caller‑provided `SELECT` safely and returns a typed payload.

Flow:
1. Safety guards (`SELECT`‑only; strip trailing `;`).
2. Dialect: `SqlglotService.auto_transpile_for_database()` and `validate()`.
3. Execute via SQLAlchemy with truncation budgets.
4. Return typed `ExecuteQueryResult` with notes and next‑step hints.

Safeguards:
- Only `SELECT` allowed; no mutations.
- Deterministic truncation by row count and per‑cell character limit.


## Install

Prerequisites:
- Python 3.13
- `uv` for environment management

Setup:

```bash
uv sync
```

Key environment variables (via `.env`):
- `NL2SQL_MCP_DATABASE_URL` (required)
- Result budgets: `NL2SQL_MCP_ROW_LIMIT`, `NL2SQL_MCP_MAX_CELL_CHARS`


## Run

Start the MCP server:

```bash
uv run nl2sql-mcp
# or
uv run python -m nl2sql_mcp.server
```

Try the local harnesses (require a live DB and `.env`):

```bash
# Schema intelligence demo
uv run python scripts/test_intelligence_harness.py "show sales by region"

# SQLGlot helpers demo
uv run python scripts/test_sqlglot_harness.py "select top 10 * from dbo.Customers"

# execute_query demo
NL2SQL_MCP_EXAMPLE_SQL='SELECT 1 AS one' uv run python scripts/test_execute_query_harness.py
```

FastMCP documentation: https://gofastmcp.com/llms.txt


## Development

Formatting, lint, types, and tests:

```bash
uv run ruff format .
uv run ruff check --fix .
uv run basedpyright
uv run pytest -q
```

Project structure:
- `src/nl2sql_mcp/` — main package (server, intelligence, services, builders)
- `scripts/` — local harnesses and demos
- `tests/` — test suite
- `docs/`, `examples/`, `data/` — reference and samples

Coding standards:
- Python 3.13, strict type checking, Pydantic/dataclasses for structured data
- Pure functions and dependency injection for testability
- No hard‑coded schema logic; engine‑agnostic via SQLAlchemy


## Supported Dialects

Validation/transpile support via `sqlglot` for:
`sql`, `postgres`, `mysql`, `sqlite`, `tsql`, `oracle`, `snowflake`, `bigquery`.


## Notes

- Embeddings are optional at runtime; retrieval falls back to lexical methods.
- The schema service is initialized once per process and exposes readiness state for clients.
