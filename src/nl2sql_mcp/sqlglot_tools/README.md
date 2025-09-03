# SQLGlot Tools: Dialect & SQL Helpers

Typed, LLM‑friendly helpers around [sqlglot] used by the MCP server and agents. Exposes a small set of side‑effect‑free services and a tool registration module.

## Service API (`SqlglotService`)

- `validate(req: SqlValidationRequest) -> SqlValidationResult`
- `transpile(req: SqlTranspileRequest) -> SqlTranspileResult`
- `auto_transpile_for_database(req: SqlAutoTranspileRequest) -> SqlAutoTranspileResult`
- `optimize(req: SqlOptimizeRequest) -> SqlOptimizeResult`
- `metadata(req: SqlMetadataRequest) -> SqlMetadataResult`
- `assist_error(req: SqlErrorAssistRequest) -> SqlErrorAssistResult`
- `map_sqlalchemy_to_sqlglot(sa_dialect: str) -> Dialect`

All methods are pure and return typed results instead of raising for common user errors.

## MCP Tools

`register_sqlglot_tools(mcp, service, dialect_provider)` registers:

- `sql_validate(sql)`
- `sql_transpile_to_database(sql, source_dialect)`
- `sql_auto_transpile_for_database(sql)`
- `sql_optimize_for_database(sql, schema_map?)`
- `sql_extract_metadata(sql)`
- `sql_assist_from_error(sql, error_message)`

The active dialect is provided via `dialect_provider()` (e.g., mapped from SQLAlchemy through `SchemaServiceManager`).

## Models

See `models.py` for request/response types. Supported `Dialect` literals:
`"sql" | "postgres" | "mysql" | "sqlite" | "tsql" | "oracle" | "snowflake" | "bigquery"`.

## Testing

Unit tests live in `tests/test_sqlglot_tools.py` and cover:
- parsing/validation, metadata extraction
- transpiling TOP->LIMIT
- optimizer round‑trip
- error assistance hints
- auto‑transpile with dialect detection

