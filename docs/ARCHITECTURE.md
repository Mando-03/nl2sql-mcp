# High-Capability MCP Server Architecture

This document records the architectural patterns that make this Model Context Protocol (MCP) server both highly capable and performant. While the reference implementation currently integrates with relational databases, every decision below is framed so it can be reused for other retrieval backends (e.g., Azure Cognitive Search, vector stores, graph APIs).

## Lifecycle Management & Initialization Discipline

- **Lifespan-bound singletons** – A FastMCP lifespan handler wires up a singleton service manager that owns all expensive resources and ensures exactly-once startup per process (`src/nl2sql_mcp/server.py:17`, `src/nl2sql_mcp/services/schema_service_manager.py:33`). This pattern avoids per-request cold starts and applies equally to non-SQL engines (swap the underlying connector, keep the lifecycle guardrails).

  ```python
  # src/nl2sql_mcp/server.py
  @asynccontextmanager
  async def lifespan(_mcp_instance: FastMCP) -> AsyncGenerator[None]:
      manager = SchemaServiceManager.get_instance()
      try:
          manager.start_background_initialization()
          yield
      finally:
          await manager.shutdown()
  ```

- **Asynchronous readiness with background threads** – Initialization spins up a daemon thread that builds the knowledge base while the server continues accepting health probes (`src/nl2sql_mcp/services/schema_service_manager.py:85`). Awaiters can block on readiness when they truly need the resources, making the design safe for slower backends.

  ```python
  # src/nl2sql_mcp/services/schema_service_manager.py
  def start_background_initialization(self) -> None:
      with self._thread_lock:
          if self._state.phase in {SchemaInitPhase.STARTING, SchemaInitPhase.RUNNING,
                                   SchemaInitPhase.READY}:
              return
          self._state = replace(self._state, phase=SchemaInitPhase.STARTING,
                                started_at=time.time())

          def _runner() -> None:
              self._state = replace(self._state, phase=SchemaInitPhase.RUNNING)
              try:
                  self._initialize_sync()
              except Exception as exc:
                  self._state = replace(self._state, phase=SchemaInitPhase.FAILED,
                                        error_message=str(exc))
              else:
                  self._state = replace(self._state, phase=SchemaInitPhase.READY,
                                        completed_at=time.time())
                  self._start_background_enrichment()
              finally:
                  self._thread_ready.set()

          threading.Thread(target=_runner, name="schema-init", daemon=True).start()
  ```

- **Observable state machine** – Typed lifecycle enums and state snapshots expose whether initialization is `IDLE`, `RUNNING`, `READY`, etc. (`src/nl2sql_mcp/services/state.py:7`). Any backend-specific bring-up (e.g., Azure Search index hydration) can map to the same state transitions, keeping tooling consistent.

  ```python
  # src/nl2sql_mcp/services/state.py
  class SchemaInitPhase(Enum):
      IDLE = auto()
      STARTING = auto()
      RUNNING = auto()
      READY = auto()
      FAILED = auto()
      STOPPED = auto()

  @dataclass(frozen=True)
  class SchemaInitState:
      phase: SchemaInitPhase
      started_at: float | None = None
      completed_at: float | None = None
      error_message: str | None = None
      attempts: int = 0
  ```

## Incremental Knowledge-Base Construction

- **Fast-start then enrich** – The first pass uses conservative limits (e.g., reflect ≤300 tables, skip FK joins) to return a working card quickly, then a secondary daemon completes deep enrichment (`src/nl2sql_mcp/services/schema_service_manager.py:329`, `src/nl2sql_mcp/schema_tools/explorer.py:345`). The tactic generalizes: an Azure Search adapter could seed top documents immediately and expand with slow metadata later.

  ```python
  # src/nl2sql_mcp/services/schema_service_manager.py
  def _start_background_enrichment(self) -> None:
      if self._enrich_in_progress or self._enrich_completed_at is not None:
          return
      self._enrich_in_progress = True

      def _enricher() -> None:
          try:
              explorer = type(self).GLOBAL_EXPLORER
              if explorer is None:
                  raise RuntimeError("GLOBAL_EXPLORER is None in enricher")
              explorer.enrich_index()
              svc = self._schema_service
              if svc is not None:
                  svc.prime_query_resources()
          finally:
              self._enrich_in_progress = False
              self._enrich_completed_at = time.time()

      self._enrich_thread = threading.Thread(target=_enricher,
                                             name="schema-enrich", daemon=True)
      self._enrich_thread.start()
  ```

- **Reusable explorers and embedders** – Heavyweight analyzers (schema explorer, embedding model) are cached globally and only rebuilt when fingerprints change (`src/nl2sql_mcp/services/schema_service_manager.py:162`). Replace the explorer with a search-index crawler or knowledge graph introspector without touching request handlers.

  ```python
  # src/nl2sql_mcp/services/schema_service_manager.py
  def _ensure_global_explorer(self, engine: sa.Engine) -> None:
      if type(self).GLOBAL_EXPLORER is None:
          config = ConfigService.get_query_analysis_config()
          global_explorer = SchemaExplorer(engine, config)
          global_explorer.build_index()
          type(self).GLOBAL_EXPLORER = global_explorer

  def _ensure_global_embedder(self) -> None:
      if type(self).GLOBAL_EMBEDDER is None:
          config = ConfigService.get_query_analysis_config()
          try:
              type(self).GLOBAL_EMBEDDER = Embedder(model_name=config.model_name)
          except Exception:
              type(self).GLOBAL_EMBEDDER = None
  ```

- **Warm caches proactively** – Post-initialization warm-up primes retrieval indices to spare the first user request from paying the index build cost (`src/nl2sql_mcp/services/schema_service_manager.py:315`). Any backend that requires vector quantization or query planning can use the same hook.

  ```python
  # src/nl2sql_mcp/services/schema_service_manager.py
  def _initialize_sync(self) -> None:
      ...

      def _warm() -> None:
          try:
              svc = self._schema_service
              if svc is not None:
                  svc.prime_query_resources()
          except Exception:
              self._logger.debug("QueryEngine warmup skipped or failed", exc_info=True)

      threading.Thread(target=_warm, name="qe-warm", daemon=True).start()
  ```

## Query-Time Intelligence Pipeline

- **Configurable, cached query engine** – The `SchemaService` lazily instantiates a query engine keyed by a config fingerprint, ensuring recomputation happens only when the knowledge base or tuning knobs change (`src/nl2sql_mcp/services/schema_service.py:79`). Swap in a search-specific retrieval engine yet retain deterministic reuse semantics.

  ```python
  # src/nl2sql_mcp/services/schema_service.py
  def _get_query_engine(self, config: SchemaExplorerConfig) -> QueryEngine:
      card = self.explorer.card
      if not card:
          raise RuntimeError("Global schema explorer has no schema card")

      cfg_fp = self._config_fingerprint(config)
      needs_rebuild = (
          self._query_engine is None
          or self._qe_reflection_hash != card.reflection_hash
          or self._qe_config_fingerprint != cfg_fp
      )
      if needs_rebuild:
          self._query_engine = QueryEngine(card, config, embedder=self.embedder)
          self._qe_reflection_hash = card.reflection_hash
          self._qe_config_fingerprint = cfg_fp
      qe = self._query_engine
      if qe is None:
          raise RuntimeError("QueryEngine not initialized")
      return qe
  ```

- **Hybrid retrieval with graceful degradation** – Retrieval combines lexical heuristics, embeddings, and graph expansion while gracefully falling back when a capability is unavailable (`src/nl2sql_mcp/schema_tools/query_engine.py:96`, `src/nl2sql_mcp/schema_tools/retrieval.py:111`). Other backends can follow the same contract: attempt semantic search, fall back to keyword or metadata-only strategies.

  ```python
  # src/nl2sql_mcp/schema_tools/query_engine.py
  if self.embedder:
      self._build_table_embeddings()
      if self.config.build_column_index:
          self._build_column_embeddings()

  self.retrieval_engine = RetrievalEngine(
      schema_card=self.schema_card,
      embedder=self.embedder,
      table_index=self.table_index,
      column_index=self.column_index,
      lexicon_learner=self.lexicon_learner,
      lexical_cache=self._lexical_cache,
      exclude_archives=self.config.strict_archive_exclude,
  )
  ```

  ```python
  # src/nl2sql_mcp/services/schema_service.py
  if approach is RetrievalApproach.COMBINED:
      retrieval_results = query_engine.retrieval_engine.retrieve_combined(
          query, k=max_tables * 2, alpha=alpha
      )
  elif approach is RetrievalApproach.EMBEDDING_TABLE:
      rt = query_engine.retrieval_engine
      if rt and (query_engine.embedder is None or rt.table_index is None):
          retrieval_results = rt.retrieve(query, RetrievalApproach.LEXICAL, k=max_tables * 2)
      else:
          retrieval_results = query_engine.retrieval_engine.retrieve(
              query, approach, k=max_tables * 2
          )
  else:
      retrieval_results = query_engine.retrieval_engine.retrieve(
          query, approach, k=max_tables * 2
      )
  ```

- **Structured planning outputs** – Responses expose join plans, filter candidates, and clarifications in strongly typed models optimized for LLM consumption (`src/nl2sql_mcp/models.py:176`, `src/nl2sql_mcp/schema_tools/response_builders.py:41`). When targeting non-SQL stores, substitute equivalent planning artifacts (e.g., filter expressions, index facets) but keep the structured schema.

  ```python
  # src/nl2sql_mcp/schema_tools/response_builders.py
  return QuerySchemaResult(
      query=query,
      relevant_tables=relevant_tables,
      join_examples=join_examples,
      suggested_approach=suggested_approach,
      key_columns=key_columns,
      main_table=main_table,
      join_plan=join_plan,
      group_by_candidates=group_by_candidates,
      filter_candidates=filter_candidates,
      selected_columns=selected_columns,
      clarifications=clarifications,
      assumptions=assumptions,
      confidence=confidence,
      draft_sql=draft_sql,
      status=status,
      next_action=next_action,
  )
  ```

## Execution Guardrails & Result Governance

- **Policy-first execution flow** – All runtime execution routes through a small, dependency-injected runner that enforces read-only semantics, normalizes requests, and attaches assistive guidance on failure (`src/nl2sql_mcp/execute/runner.py:33`). The same flow can wrap any backend client—swap SQLAlchemy for a REST client while preserving validation and truncation guards.

  ```python
  # src/nl2sql_mcp/execute/runner.py
  def run_execute_flow(
      *,
      sql: str,
      engine: sa.Engine,
      glot: SqlglotService,
      active_dialect: Dialect,
      limits: ExecutionLimits,
  ) -> ExecuteQueryResult:
      enforce_select_only(sql)
      base_sql = strip_trailing_semicolon(sql)
      trans = glot.auto_transpile_for_database(
          SqlAutoTranspileRequest(sql=base_sql, target_dialect=active_dialect)
      )
      validation = glot.validate(SqlValidationRequest(sql=trans.sql, dialect=active_dialect))

      try:
          with engine.connect() as conn:
              result = conn.execute(sa.text(trans.sql))
              cols = list(result.keys())
              raw_rows = result.mappings().fetchmany(limits.row_limit + 1)
              rows = _truncate_rows(raw_rows, cols, limits.row_limit, limits.max_cell_chars)
      except SQLAlchemyError as exc:
          helpres = glot.assist_error(
              SqlErrorAssistRequest(sql=trans.sql, error_message=str(exc), dialect=active_dialect)
          )
          return ExecuteQueryResult(
              sql=trans.sql,
              execution_error=str(exc),
              status="error",
              assist_notes=helpres.suggested_fixes or None,
              next_action="refine_plan",
              execution={"dialect": active_dialect, "rows_returned": 0, ...},
          )

      truncated = len(raw_rows) > limits.row_limit
      summary = f"{min(len(raw_rows), limits.row_limit)} row(s), {len(cols)} column(s)"
      if truncated:
          summary += "; truncated"

      return ExecuteQueryResult(
          sql=trans.sql,
          results=rows,
          status="ok",
          next_action="refine_plan" if truncated else None,
          result_sample_summary=summary,
          execution={"dialect": active_dialect, "rows_returned": len(rows), ...},
      )
  ```

- **Dialect abstraction via typed services** – A dedicated adapter maps runtime dialect names to sqlglot dialects and caches parse trees for speed (`src/nl2sql_mcp/sqlglot_tools/service.py:31`). In other backends, this layer would translate between transport-specific syntax or query languages (e.g., KQL, Lucene).

  ```python
  # src/nl2sql_mcp/sqlglot_tools/service.py
  SQLALCHEMY_TO_SQLGLOT: dict[str, Dialect] = {
      "postgresql": "postgres",
      "mysql": "mysql",
      "mssql": "tsql",
      ...
  }

  def map_sqlalchemy_to_sqlglot(sa_dialect_name: str) -> Dialect:
      return SQLALCHEMY_TO_SQLGLOT.get(sa_dialect_name.lower(), "sql")

  @lru_cache(maxsize=256)
  def _cached_parse(sql: str, dialect: Dialect) -> sqlglot.Expression | None:
      return sqlglot.parse_one(sql, dialect=dialect)
  ```

- **Config-driven budgets** – Row limits, payload caps, and per-cell truncation are centralized in a configuration service with environment overrides (`src/nl2sql_mcp/services/config_service.py:123`). Replace these with service-specific quotas (e.g., search result page size) while keeping the same governance knobs.

  ```python
  # src/nl2sql_mcp/services/config_service.py
  class ConfigService:
      @staticmethod
      def result_row_limit() -> int:
          val = os.getenv("NL2SQL_MCP_ROW_LIMIT", "200")
          return max(1, int(val))

      @staticmethod
      def result_max_cell_chars() -> int:
          val = os.getenv("NL2SQL_MCP_MAX_CELL_CHARS", "200")
          return max(10, int(val))

      @staticmethod
      def get_query_analysis_config() -> SchemaExplorerConfig:
          return SchemaExplorerConfig(
              per_table_rows=50,
              sample_timeout=15,
              fast_startup=True,
              max_tables_at_startup=300,
              ...
          )
  ```

## Extensibility Across Data Backends

- **Dependency injection at tool registration** – MCP tools resolve services via the manager but accept optional overrides for testing or alternate backends (`src/nl2sql_mcp/schema_tools/mcp_tools.py:34`, `src/nl2sql_mcp/execute/mcp_tools.py:26`). New adapters can be slotted in without modifying tool signatures.

  ```python
  # src/nl2sql_mcp/schema_tools/mcp_tools.py
  def register_intelligence_tools(mcp: FastMCP, manager: SchemaServiceManager | None = None) -> None:
      mgr = manager or SchemaServiceManager.get_instance()

      @mcp.tool
      async def plan_query_for_intent(...):
          schema_service = await mgr.get_schema_service()
          result = schema_service.analyze_query_schema(...)
          return result
  ```

  ```python
  # src/nl2sql_mcp/execute/mcp_tools.py
  def register_execute_query_tool(mcp: FastMCP, *, sqlglot_service: SqlglotService | None = None) -> None:
      mgr = SchemaServiceManager.get_instance()
      glot = sqlglot_service or SqlglotService()

      @mcp.tool
      async def execute_query(...):
          schema_service = await mgr.get_schema_service()
          return run_execute_flow(sql=sql, engine=schema_service.engine,
                                  glot=glot, active_dialect=dialect,
                                  limits=ExecutionLimits(...))
  ```

- **Configuration surface is backend-agnostic** – Environment-driven tunables (embedding model, startup caps, cache budgets) are agnostic to storage choice, making it simple to introduce, for example, `MCP_SEARCH_ENDPOINT` knobs alongside database URLs.

- **Business primitives, not SQL specifics** – The planners reason in terms of entities like subject areas, roles, and join purposes (`src/nl2sql_mcp/schema_tools/explorer.py:222`, `src/nl2sql_mcp/schema_tools/response_builders.py:176`). For non-tabular systems, reinterpret these primitives as collections, facets, or relationship hops while keeping the overall dialogue the same.

  ```python
  # src/nl2sql_mcp/schema_tools/explorer.py
  for table_key, table_profile in tables.items():
      table_profile.subject_area = str(merged_communities.get(table_key, -1))
      table_profile.archetype = self._classifier.classify_table(table_profile, relationship_graph)
      table_profile.summary = self._classifier.summarize_table(table_profile)
  ```

## MCP Tool Design Philosophy: Conversational Helpers

- **Intent planning as guidance, not raw metadata** – The planning tool frames its output as advice and flags uncertainty with clarifications and confidence metrics, allowing the calling LLM to request follow-up questions instead of blindly executing (`src/nl2sql_mcp/schema_tools/mcp_tools.py:43`, `src/nl2sql_mcp/schema_tools/response_builders.py:176`).

  ```python
  # src/nl2sql_mcp/schema_tools/mcp_tools.py
  @mcp.tool
  async def plan_query_for_intent(..., full_detail: bool = False, ... ) -> QuerySchemaResult:
      schema_service = await mgr.get_schema_service()
      result = schema_service.analyze_query_schema(
          request,
          max_tables,
          approach=default_approach,
          alpha=0.7,
          detail_level=default_detail,
          include_samples=False,
          max_sample_values=max_sample_values,
          max_columns_per_table=max_columns_per_table,
          join_limit=join_limit,
      )
      _logger.info("Planned query; selected %d tables", len(result.relevant_tables))
      return result
  ```

  ```python
  # src/nl2sql_mcp/schema_tools/response_builders.py
  clarifications: list[str] = []
  if main_table is None:
      clarifications.append("Which business entity should anchor this query (primary table)?")
  confidence = min(confidence, 1.0)
  draft_sql = ...  # emitted only when clarifications are empty
  return QuerySchemaResult(
      ...,
      clarifications=clarifications,
      confidence=confidence,
      draft_sql=draft_sql,
      status=status,
      next_action=next_action,
  )
  ```

- **Table inspection tools surface storytelling details** – `get_table_info` returns summaries, representative values, and relationship hints so the LLM can reason about joins and filters conversationally (`src/nl2sql_mcp/schema_tools/mcp_tools.py:166`).

  ```python
  # src/nl2sql_mcp/schema_tools/mcp_tools.py
  @mcp.tool
  async def get_table_info(..., table_key: str, include_samples: bool = True, ...) -> TableInfo:
      schema_service = await mgr.get_schema_service()
      result = schema_service.get_table_information(
          table_key,
          include_samples=include_samples,
          column_role_filter=column_role_filter,
          max_sample_values=max_sample_values,
          relationship_limit=relationship_limit,
      )
      _logger.info("Retrieved table information for %s (%d columns)", table_key, len(result.columns))
      return result
  ```

- **Execution tool collaborates on error recovery** – The execution path emits validation notes, assistive hints, and a `next_action` recommendation so the calling LLM knows whether to retry, refine, or paginate rather than treating the result as a simple data payload (`src/nl2sql_mcp/execute/mcp_tools.py:40`, `src/nl2sql_mcp/execute/runner.py:109`).

  ```python
  # src/nl2sql_mcp/execute/mcp_tools.py
  @mcp.tool
  async def execute_query(ctx: Context, sql: str) -> ExecuteQueryResult:
      schema_service = await mgr.get_schema_service()
      return run_execute_flow(
          sql=sql,
          engine=schema_service.engine,
          glot=glot,
          active_dialect=dialect,
          limits=ExecutionLimits(row_limit=row_limit, max_cell_chars=max_cell_chars),
      )
  ```

  ```python
  # src/nl2sql_mcp/execute/runner.py
  return ExecuteQueryResult(
      sql=trans.sql,
      results=rows,
      validation_notes=notes,
      recommended_next_steps=next_steps,
      status="ok",
      next_action="refine_plan" if truncated else None,
      result_sample_summary=summary,
  )
  ```

- **Error surfaces speak directly to the agent** – When preconditions fail (service not ready, table missing, SQL invalid) the tools reply via the MCP context with human-readable guidance, keeping the conversation loop tight (`src/nl2sql_mcp/schema_tools/mcp_tools.py:95`, `src/nl2sql_mcp/execute/mcp_tools.py:63`).

  ```python
  # src/nl2sql_mcp/schema_tools/mcp_tools.py
  try:
      schema_service = await mgr.get_schema_service()
  except (RuntimeError, ValueError) as exc:
      await ctx.error(f"Schema service not ready: {exc}")
      raise
  ```

  ```python
  # src/nl2sql_mcp/execute/runner.py
  except SQLAlchemyError as exc:
      assist = glot.assist_error(...)
      return ExecuteQueryResult(
          sql=trans.sql,
          execution_error=str(exc),
          status="error",
          assist_notes=assist_notes or None,
          next_action="refine_plan",
      )
  ```

Together, these patterns transform each MCP tool from a passive data fetcher into a collaborative helper that guides the requesting LLM through planning, clarification, and safe execution, regardless of the underlying backend.

## Operational Observability & Fault Handling

- **Explicit health and readiness probes** – A lightweight `/health` endpoint and the `get_init_status` tool expose diagnostic details without invoking heavy services (`src/nl2sql_mcp/server.py:40`, `src/nl2sql_mcp/schema_tools/mcp_tools.py:296`).
- **Best-effort resilience** – Background tasks catch and log errors while keeping the main service available (`src/nl2sql_mcp/services/schema_service_manager.py:337`). When pointed at flakier backends, this strategy keeps partial capability online and surfaces actionable errors to the caller.

## Design Principles Recap

1. **Type-Safe Contracts** – Typed models for every MCP tool guarantee that downstream consumers receive predictable structures, regardless of backend.
2. **Fast-Ready, Deep-Enrich** – Start with a minimal, operational index; enrich asynchronously.
3. **Cache Everything Deterministically** – Use fingerprints and config hashes to control rebuilds and keep response times stable.
4. **Graceful Degradation** – Every advanced feature (embeddings, graph expansion, dialect-specific SQL) has a fallback path that still produces useful output.
5. **Pluggable Connectors** – All heavy lifting is isolated behind services that can be reimplemented for other storage technologies without touching tool interfaces.

Adopting these patterns lets future MCP servers deliver consistent, low-latency experiences whether they index relational schemas, search documents, or traverse knowledge graphs.
