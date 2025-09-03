# NL2SQL MCP Services

Service layer that centralizes configuration, schema exploration orchestration, and lifecycle management for the MCP server.

## Modules

- `config_service.py`: configuration + engine creation
- `schema_service.py`: query‑time schema analysis APIs
- `schema_service_manager.py`: singleton lifecycle + background init
- `state.py`: typed init state used by the manager

## Responsibilities

- Build SQLAlchemy engines with optional plugins (e.g., `geoalchemy2`) and MSSQL spatial type registration.
- Create tuned `SchemaExplorerConfig` for query analysis.
- Host a single `SchemaService` wired to a global `SchemaExplorer` and optional `Embedder`.
- Provide readiness and error state to MCP tools.

## Key APIs

- `ConfigService.get_database_url() -> str`
- `ConfigService.create_database_engine(url: str) -> sa.Engine`
  (LLM configuration removed with legacy agent deprecation.)
- `ConfigService.get_query_analysis_config() -> SchemaExplorerConfig`
- `SchemaService.analyze_query_schema(query, max_tables=5, ...) -> QuerySchemaResult`
- `SchemaService.get_database_overview(...) -> DatabaseSummary`
- `SchemaService.get_table_information(table_key, ...) -> TableInfo`
- `SchemaService.find_tables(query, limit=10, approach=..., alpha=0.7) -> list[TableSearchHit]`
- `SchemaService.find_columns(keyword, limit=25, by_table=None) -> list[ColumnSearchHit]`
- `SchemaServiceManager.get_instance().start_background_initialization()`
- `SchemaServiceManager.get_instance().get_schema_service() -> SchemaService`
- `SchemaServiceManager.status() -> SchemaInitState` (phases: IDLE/STARTING/RUNNING/READY/FAILED/STOPPED)

## Initialization Model

`SchemaServiceManager` runs a once‑per‑process background initialization:

- Creates the engine and fingerprints the DB URL.
- Builds a global `SchemaExplorer` by reflecting, sampling, profiling, graphing, and summarizing.
- Builds a global `Embedder` when `sentence-transformers` is available; otherwise disables embeddings gracefully.
- Publishes readiness and error details for MCP clients via `get_init_status`.

## Environment

- `NL2SQL_MCP_DATABASE_URL` (required)
  (No LLM environment variables are required.)

## Notes

- All public methods are typed and designed for testability; pure logic is separated from I/O where feasible.
- Embedding usage is optional at runtime; retrieval falls back to lexical methods when disabled.
