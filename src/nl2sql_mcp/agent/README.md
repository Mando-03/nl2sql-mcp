# NL2SQL MCP Agent: ask_database

This package contains a focused LLM agent that turns a natural‑language question into one safe, executable `SELECT` query and returns concise, typed results for downstream orchestration.

- Tool: `ask_database(question: str)`
- Inputs: user question, active dialect, schema context (from `schema_tools`)
- Outputs: `AskDatabaseResult` (typed, compact, LLM‑friendly)

## Flow Overview

1. Schema focus: call `SchemaService.analyze_query_schema()` to gather relevant tables, joins, and key columns.
2. Planning: a small PydanticAI `Agent[AgentDeps, LlmSqlPlan]` proposes exactly one `SELECT`.
3. Safety: reject non‑SELECT operations; strip trailing semicolon.
4. Dialect handling: normalize/transpile with `SqlglotService.auto_transpile_for_database()` and `validate()`.
5. Execution: run via SQLAlchemy with row and cell truncation safeguards.
6. Result shaping: return `AskDatabaseResult` with validation notes and next‑step hints.

## Key Types

- `AgentDeps`: active dialect, `row_limit`, `max_cell_chars`, `max_payload_bytes`.
- `LlmSqlPlan`: intent, clarifications_needed, sql, confidence.
- `AskDatabaseResult`: question, schema_context, sql, execution metadata, rows, notes, recommendations, confidence, status.

See `src/nl2sql_mcp/agent/models.py` and `agent.py` for full signatures and docstrings.

## Integration

- Registration: `register_ask_database_tool(FastMCP, sqlglot_service?)` in `mcp_tools.py`.
- Dependencies:
  - `SchemaServiceManager.get_instance()` provides the initialized `SchemaService` and engine.
  - `ConfigService.get_llm_config()` supplies provider/model and tunables via env.
  - `SqlglotService` handles validation/transpile/metadata.

## Configuration

Environment variables consumed through `ConfigService`:

- Database: `NL2SQL_MCP_DATABASE_URL` (required)
- Result budgets: `NL2SQL_MCP_ROW_LIMIT`, `NL2SQL_MCP_MAX_CELL_CHARS`, `NL2SQL_MCP_MAX_RESULT_BYTES`
- LLM: `NL2SQL_MCP_LLM_PROVIDER`, `NL2SQL_MCP_LLM_MODEL` (+ optional temperature/top_p/top_k/max tokens)

## Guarantees & Safeguards

- Only `SELECT` statements are allowed (simple preflight guard).
- Dialect normalization ensures `LIMIT`/`TOP` and quoting are appropriate.
- Results are truncated deterministically by rows and cell length to honor payload budgets.

## Testing & Extensibility

- The agent is pure at the core and designed for DI: pass an explicit `SqlglotService`, `Engine`, and `LLMConfig` for tests.
- Add ranking or retry strategies by extending `LlmSqlPlan` and `run_ask_flow()` while keeping signatures typed.

