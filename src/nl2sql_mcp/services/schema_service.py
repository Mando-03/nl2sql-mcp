"""Schema service for nl2sql-mcp.

This module provides the main business logic orchestration for database schema
analysis operations. It coordinates between the schema_tools modules and
response builders to provide high-level schema analysis capabilities.
"""

from __future__ import annotations

from typing import Literal, cast

import pyodbc
import sqlalchemy as sa

from nl2sql_mcp.models import (
    ColumnSearchHit,
    DatabaseSummary,
    QuerySchemaResult,
    TableInfo,
    TableSearchHit,
)
from nl2sql_mcp.schema_tools.constants import RetrievalApproach
from nl2sql_mcp.schema_tools.embeddings import Embedder
from nl2sql_mcp.schema_tools.explorer import SchemaExplorer
from nl2sql_mcp.schema_tools.models import SchemaExplorerConfig
from nl2sql_mcp.schema_tools.query_engine import QueryEngine
from nl2sql_mcp.schema_tools.response_builders import (
    DatabaseSummaryBuilder,
    QuerySchemaResultBuilder,
    TableInfoBuilder,
)
from nl2sql_mcp.schema_tools.utils import tokens_from_text
from nl2sql_mcp.services.config_service import ConfigService

pyodbc.pooling = False


class SchemaService:
    """Service for orchestrating database schema analysis operations."""

    def __init__(
        self, engine: sa.Engine, explorer: SchemaExplorer, embedder: Embedder | None = None
    ) -> None:
        """Initialize schema service with database engine and schema explorer.

        Args:
            engine: SQLAlchemy database engine
            explorer: Pre-built SchemaExplorer instance
            embedder: Optional pre-built Embedder instance
        """
        self.engine = engine
        self.explorer = explorer
        self.embedder = embedder

        # Lazily-built, reusable QueryEngine tied to the explorer's SchemaCard.
        # We rebuild only when the underlying schema fingerprint changes or
        # when the effective query-analysis config changes.
        self._query_engine: QueryEngine | None = None
        self._qe_reflection_hash: str | None = None
        self._qe_config_fingerprint: str | None = None

    # ---- internal helpers -------------------------------------------------
    def _config_fingerprint(self, config: SchemaExplorerConfig) -> str:
        """Compute a stable fingerprint for QueryEngine-relevant config.

        Args:
            config: The SchemaExplorerConfig used for query analysis.

        Returns:
            A short string key that changes when QE-affecting knobs change.
        """
        # Only include knobs that affect embeddings/indices/expansion.
        # Keep format simple and entirely static-typed.
        return (
            f"model={config.model_name}|cols={int(config.build_column_index)}"
            f"|maxcols={config.max_cols_for_embeddings}|exp={config.expander}"
        )

    def _get_query_engine(self, config: SchemaExplorerConfig) -> QueryEngine:
        """Return a cached QueryEngine, rebuilding only when needed.

        Reuses table/column indices, token lexicon, and lexical cache across
        requests to avoid repeated vectorization and Annoy builds.

        Args:
            config: The query-analysis configuration.

        Returns:
            A ready QueryEngine instance bound to the current SchemaCard.

        Raises:
            RuntimeError: If a schema card is not available.
        """
        card = self.explorer.card
        if not card:
            msg = "Global schema explorer has no schema card"
            raise RuntimeError(msg)

        cfg_fp = self._config_fingerprint(config)
        needs_rebuild = (
            self._query_engine is None
            or self._qe_reflection_hash != card.reflection_hash
            or self._qe_config_fingerprint != cfg_fp
        )
        if needs_rebuild:
            # Build once; QueryEngine internally constructs lexical cache,
            # embeddings, and Annoy indices. Subsequent calls reuse these.
            self._query_engine = QueryEngine(card, config, embedder=self.embedder)
            self._qe_reflection_hash = card.reflection_hash
            self._qe_config_fingerprint = cfg_fp
        # basedpyright: assure non-None before returning
        assert self._query_engine is not None
        return self._query_engine

    # Public hook used by the manager to warm indices after init/enrichment.
    def prime_query_resources(self) -> None:
        """Warm QueryEngine caches/indices for the current schema card.

        Builds the reusable QueryEngine once so the first user request does
        not pay the embedding/index construction cost.
        """
        config = ConfigService.get_query_analysis_config()
        _ = self._get_query_engine(config)

    def analyze_query_schema(  # noqa: PLR0913 - explicit controls are intentional
        self,
        query: str,
        max_tables: int = 5,
        *,
        approach: RetrievalApproach = RetrievalApproach.COMBINED,
        alpha: float = 0.7,
        detail_level: str = "standard",
        include_samples: bool = False,
        max_sample_values: int = 3,
        max_columns_per_table: int = 20,
        join_limit: int = 8,
    ) -> QuerySchemaResult:
        """Analyze database schema for a specific natural language query.

        Args:
            query: Natural language query to analyze
            max_tables: Maximum number of tables to include (default: 5)

        Returns:
            QuerySchemaResult with relevant schema information

        Raises:
            RuntimeError: If schema exploration fails
        """
        # Ensure we have a valid schema card
        if not self.explorer.card:
            msg = "Global schema explorer has no schema card"
            raise RuntimeError(msg)

        # Get configuration and a cached QueryEngine (reused across calls)
        config = ConfigService.get_query_analysis_config()
        query_engine = self._get_query_engine(config)
        if not query_engine.retrieval_engine or not query_engine.graph_expander:
            msg = "Failed to initialize query engine components"
            raise RuntimeError(msg)

        # Get relevant tables using retrieval + expansion
        if approach is RetrievalApproach.COMBINED:
            retrieval_results = query_engine.retrieval_engine.retrieve_combined(
                query, k=max_tables * 2, alpha=alpha
            )
        else:
            retrieval_results = query_engine.retrieval_engine.retrieve(
                query, approach, k=max_tables * 2
            )
        seed_tables = [table_key for table_key, _ in retrieval_results[:max_tables]]
        expanded_tables = query_engine.graph_expander.expand(seed_tables, k=max_tables)

        # Build and return query schema result
        valid = {"minimal", "standard", "full"}
        dl: Literal["minimal", "standard", "full"] = cast(
            Literal["minimal", "standard", "full"],
            detail_level if detail_level in valid else "standard",
        )
        return QuerySchemaResultBuilder.build(
            query,
            expanded_tables,
            self.explorer,
            detail_level=dl,
            include_samples=include_samples,
            max_sample_values=max_sample_values,
            max_columns_per_table=max_columns_per_table,
            join_limit=join_limit,
        )

    def get_database_overview(
        self, *, include_subject_areas: bool = False, area_limit: int = 8
    ) -> DatabaseSummary:
        """Get high-level database overview information.

        Returns:
            DatabaseSummary with database structure and patterns

        Raises:
            RuntimeError: If schema exploration fails
        """
        # Build and return database summary using the global explorer
        return DatabaseSummaryBuilder.build(
            self.explorer, include_subject_areas=include_subject_areas, area_limit=area_limit
        )

    def get_table_information(
        self,
        table_key: str,
        *,
        include_samples: bool = True,
        column_role_filter: list[str] | None = None,
        max_sample_values: int = 5,
        relationship_limit: int | None = None,
    ) -> TableInfo:
        """Get comprehensive information about a specific table.

        Args:
            table_key: Table identifier in 'schema.table' format
            include_samples: Whether to include sample values in column details

        Returns:
            TableInfo with comprehensive table details

        Raises:
            RuntimeError: If schema exploration fails
            KeyError: If table not found
        """
        # Build and return table information using the global explorer
        return TableInfoBuilder.build(
            table_key,
            self.explorer,
            include_samples=include_samples,
            column_role_filter=column_role_filter,
            max_sample_values=max_sample_values,
            relationship_limit=relationship_limit,
        )

    # --- discovery utilities -------------------------------------------------

    def find_tables(
        self,
        query: str,
        limit: int = 10,
        *,
        approach: RetrievalApproach = RetrievalApproach.COMBINED,
        alpha: float = 0.7,
    ) -> list[TableSearchHit]:
        """Find tables relevant to a query using configured retrieval.

        Returns a list of hits with scores and brief summaries.
        """
        if not self.explorer.card:
            msg = "Global schema explorer has no schema card"
            raise RuntimeError(msg)

        config = ConfigService.get_query_analysis_config()
        query_engine = self._get_query_engine(config)
        if not query_engine.retrieval_engine:
            msg = "Failed to initialize retrieval engine"
            raise RuntimeError(msg)

        if approach is RetrievalApproach.COMBINED:
            items = query_engine.retrieval_engine.retrieve_combined(query, k=limit, alpha=alpha)
        else:
            items = query_engine.retrieval_engine.retrieve(query, approach, k=limit)

        hits: list[TableSearchHit] = []
        for table_key, score in items[:limit]:
            tp = self.explorer.card.tables.get(table_key)
            summary = tp.summary if tp else None
            hits.append(TableSearchHit(table=table_key, score=float(score), summary=summary))
        return hits

    def find_columns(  # noqa: PLR0912 - dual strategy (embedding/lexical)
        self, keyword: str, limit: int = 25, *, by_table: str | None = None
    ) -> list[ColumnSearchHit]:
        """Find columns matching a keyword, optionally within a specific table.

        Uses column embeddings when available; falls back to lexical token match.
        """
        if not self.explorer.card:
            msg = "Global schema explorer has no schema card"
            raise RuntimeError(msg)

        config = ConfigService.get_query_analysis_config()
        query_engine = self._get_query_engine(config)

        results: list[ColumnSearchHit] = []
        seen: set[tuple[str, str]] = set()

        # Prefer embeddings if index available
        if (
            keyword.strip()
            and query_engine.retrieval_engine
            and query_engine.retrieval_engine.column_index
        ):
            vec = query_engine.embedder.encode([keyword])[0] if query_engine.embedder else None
            if vec is not None:
                hits = query_engine.retrieval_engine.column_index.search(vec, k=max(limit * 2, 50))
                for label, _score in hits:
                    if "::" not in label:
                        continue
                    table_key, col = label.split("::", 1)
                    if by_table and table_key != by_table:
                        continue
                    tp = self.explorer.card.tables.get(table_key)
                    if not tp:
                        continue
                    col_prof = next((c for c in tp.columns if c.name == col), None)
                    if not col_prof:
                        continue
                    key = (table_key, col)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        ColumnSearchHit(
                            table=table_key,
                            column=col,
                            role=col_prof.role,
                            data_type=col_prof.type,
                        )
                    )
                    if len(results) >= limit:
                        return results

        # Fallback lexical search

        tokens = set(tokens_from_text(keyword))
        if not tokens:
            return results
        scored: list[tuple[float, ColumnSearchHit]] = []
        for table_key, tp in self.explorer.card.tables.items():
            if by_table and table_key != by_table:
                continue
            for col in tp.columns:
                name_toks = set(tokens_from_text(col.name))
                role_toks: set[str] = set(tokens_from_text(col.role)) if col.role else set[str]()
                hit_score = 0.0
                if tokens & name_toks:
                    hit_score += 1.0
                if tokens & role_toks:
                    hit_score += 0.3
                if hit_score > 0:
                    scored.append(
                        (
                            hit_score,
                            ColumnSearchHit(
                                table=table_key, column=col.name, role=col.role, data_type=col.type
                            ),
                        )
                    )
        scored.sort(key=lambda x: -x[0])
        for _s, item in scored[: max(0, limit - len(results))]:
            results.append(item)
        return results

    # Deprecated cache APIs removed to minimize surface area

    @classmethod
    def from_database_url(
        cls, database_url: str, explorer: SchemaExplorer, embedder: Embedder | None = None
    ) -> SchemaService:
        """Create SchemaService from database URL and explorer.

        Args:
            database_url: Database connection URL
            explorer: Pre-built SchemaExplorer instance
            embedder: Optional pre-built Embedder instance

        Returns:
            SchemaService instance
        """
        engine = ConfigService.create_database_engine(database_url)
        return cls(engine, explorer, embedder)

    @classmethod
    def from_environment(
        cls, explorer: SchemaExplorer, embedder: Embedder | None = None
    ) -> SchemaService:
        """Create SchemaService from environment configuration.

        Args:
            explorer: Pre-built SchemaExplorer instance
            embedder: Optional pre-built Embedder instance

        Returns:
            SchemaService instance using environment variables

        Raises:
            ValueError: If required environment variables are not set
        """
        database_url = ConfigService.get_database_url()
        return cls.from_database_url(database_url, explorer, embedder)
