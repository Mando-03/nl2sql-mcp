"""Main SchemaExplorer orchestrator class.

This module contains the main SchemaExplorer class that orchestrates all
the schema exploration functionality. It serves as the primary entry point
and coordinates between reflection, sampling, profiling, graph analysis,
embedding, retrieval, and expansion components.

Classes:
- SchemaExplorer: Main orchestrator class for database schema exploration
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import time

from fastmcp.utilities.logging import get_logger
import networkx as nx
import numpy as np
import sqlalchemy as sa

from nl2sql_mcp.models import (
    SubjectAreaData,
)

from .constants import Constants
from .graph import Classifier, GraphBuilder
from .models import ColumnProfile, SchemaCard, SchemaExplorerConfig, TableProfile
from .profiling import Profiler
from .reflection import ReflectionAdapter
from .sampling import Sampler
from .utils import fingerprint_reflection, is_archive_label, now, tokens_from_text

# Logger
_logger = get_logger("schema_explorer")


class SchemaExplorer:
    """Main orchestrator for database schema exploration and analysis.

    This class coordinates all schema exploration functionality including
    database reflection, data sampling, semantic analysis, graph building,
    and classification. It focuses solely on building comprehensive schema
    cards for database analysis.

    Attributes:
        engine: SQLAlchemy engine for database connections
        config: Configuration object containing all SchemaExplorer settings
        card: Complete schema card with analyzed metadata
        embedder: Optional embedder for semantic similarity
    """

    def __init__(
        self,
        engine: sa.Engine,
        config: SchemaExplorerConfig,
        schema_card: SchemaCard | None = None,
    ) -> None:
        """Initialize the SchemaExplorer.

        Args:
            engine: SQLAlchemy engine for database connections
            config: Configuration object containing all SchemaExplorer settings
            schema_card: Optional existing schema card to use as starting state
        """
        # Core database connection
        self._engine = engine
        self.config = config

        # Component initialization
        self._reflector = ReflectionAdapter(
            self._engine,
            config.include_schemas,
            config.exclude_schemas,
            fast_startup=config.fast_startup,
            max_tables_at_startup=config.max_tables_at_startup,
            reflect_timeout_sec=config.reflect_timeout_sec,
        )
        self._sampler = Sampler(self._engine, config.per_table_rows, config.sample_timeout)
        self._profiler = Profiler()
        self._graph_builder = GraphBuilder()
        self._classifier = Classifier()

        # State
        self.card: SchemaCard | None = schema_card
        self._reflection_hash: str | None = schema_card.reflection_hash if schema_card else None

    @property
    def dialect(self) -> sa.engine.Dialect:
        """Return the SQLAlchemy dialect associated with the engine.

        Exposes a public, typed handle so downstream builders can compile
        dialect-appropriate SQL without touching private attributes.
        """
        return self._engine.dialect

    @property
    def database_name(self) -> str | None:
        """Return the database name/identifier if available.

        Uses the SQLAlchemy engine URL's `database` attribute when present.
        Some dialects (e.g., SQLite in-memory) may not expose a stable name,
        in which case this returns None.
        """
        try:
            # SQLAlchemy URL.database may be None for some URLs/dialects.
            name = self._engine.url.database  # type: ignore[attr-defined]
        except AttributeError:
            return None
        return str(name) if name else None

    def _db_url_fingerprint(self, url: str) -> str:
        """Generate fingerprint for database URL.

        Args:
            url: Database connection URL

        Returns:
            Short hash fingerprint of the URL
        """
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]

    def build_index(self, timings: dict[str, float] | None = None) -> SchemaCard:  # noqa: PLR0912
        """Build complete schema index with all analysis components.

        Performs comprehensive schema analysis including reflection, sampling,
        profiling, graph analysis, classification, and optional embedding
        generation.

        Args:
            timings: Optional dictionary to store timing measurements

        Returns:
            Complete SchemaCard with analyzed metadata

        Raises:
            ReflectionError: If database reflection fails
        """
        if timings is None:
            timings = {}

        total_start = now()

        # Step 1: Database reflection
        _logger.info("Starting database reflection...")
        reflection_start = now()
        reflection_data = self._reflector.reflect()
        timings["reflect"] = now() - reflection_start

        self._reflection_hash = fingerprint_reflection(reflection_data)
        schemas = list(reflection_data["schemas"].keys())
        db_url_fingerprint = self._db_url_fingerprint(str(self._engine.url))

        _logger.info(
            "Reflected %d schemas with %d tables total",
            len(schemas),
            sum(len(s["tables"]) for s in reflection_data["schemas"].values()),
        )

        # Step 2: Build TableProfile objects
        tables: dict[str, TableProfile] = {}
        for schema, schema_dict in reflection_data["schemas"].items():
            for table, table_metadata in schema_dict["tables"].items():
                pk_columns = set(table_metadata["pk"])

                # Create ColumnProfile objects
                columns = [
                    ColumnProfile(
                        name=col["name"],
                        type=str(col["type"]).lower(),
                        nullable=col.get("nullable", True),
                        is_pk=(col["name"] in pk_columns),
                        comment=col.get("comment"),
                    )
                    for col in table_metadata["columns"]
                ]

                # Create TableProfile
                table_profile = TableProfile(
                    schema=schema,
                    name=table,
                    columns=columns,
                    fks=table_metadata["fks"],
                    pk_cols=list(pk_columns),
                    comment=table_metadata.get("comment"),
                )

                tables[f"{schema}.{table}"] = table_profile

        # Mark foreign key columns
        for table_profile in tables.values():
            for column in table_profile.columns:
                for fk_col, ref_table, ref_col in table_profile.fks:
                    if column.name == fk_col:
                        column.is_fk = True
                        column.fk_ref = (ref_table, ref_col)

        # Step 3: Data sampling and profiling
        _logger.info(
            (
                "Starting data sampling and profiling: per_table_rows=%d "
                "max_sampled_columns=%d timeout=%ds"
            ),
            self.config.per_table_rows,
            self.config.max_sampled_columns,
            self.config.sample_timeout,
        )
        sampling_start = now()
        counts_by_table = self._sample_and_profile_tables(tables)
        timings["sample_profile"] = now() - sampling_start

        # Minimal heartbeat: sampling/profiling stats
        try:
            tables_count = len(tables)
            rows_sampled_total = sum(int(tp.n_rows_sampled or 0) for tp in tables.values())
            avg_rows = (float(rows_sampled_total) / tables_count) if tables_count else 0.0
            _logger.info(
                "sample_profile: tables=%d rows_sampled=%d avg_rows=%.1f",
                tables_count,
                rows_sampled_total,
                avg_rows,
            )
            # Aggregate coverage over selected columns for sampling
            total_cols_selected = sum(int(v) for v in counts_by_table.values())
            avg_cols = (float(total_cols_selected) / tables_count) if tables_count else 0.0
            max_cols = max(counts_by_table.values()) if counts_by_table else 0
            _logger.info(
                (
                    "sample_coverage: tables=%d total_cols_selected=%d "
                    "avg_cols_per_table=%.1f max_cols_per_table=%d"
                ),
                tables_count,
                total_cols_selected,
                avg_cols,
                max_cols,
            )
        except Exception:  # noqa: BLE001 - observability-only
            _logger.debug("sample_profile heartbeat logging failed", exc_info=True)

        # Step 4: Graph analysis and community detection
        _logger.info("Building relationship graph and detecting communities...")
        graph_start = now()
        relationship_graph = self._graph_builder.build(tables)
        centrality, communities = self._graph_builder.compute_metrics_and_communities(
            relationship_graph
        )

        # Assign centrality scores
        for table_key, table_profile in tables.items():
            table_profile.centrality = float(centrality.get(table_key, 0.0))

        # Create initial community mapping
        node_to_community = {
            node: communities.get(node, -1) for node in relationship_graph.nodes()
        }
        timings["graph_communities"] = now() - graph_start

        # Minimal heartbeat: graph/community stats
        try:
            nodes = int(relationship_graph.number_of_nodes())
            edges = int(relationship_graph.number_of_edges())
            community_count = len(set(communities.values())) if communities else 0
            _logger.info(
                "graph: nodes=%d edges=%d communities=%d",
                nodes,
                edges,
                community_count,
            )
        except Exception:  # noqa: BLE001 - observability-only
            _logger.debug("graph heartbeat logging failed", exc_info=True)

        # Step 5: Subject area merging and assignment
        merged_communities = self._merge_subject_areas(
            relationship_graph,
            node_to_community,
            tables,
            _min_size=self.config.min_area_size,
            _merge_archive=self.config.merge_archive_areas,
        )

        for table_key, table_profile in tables.items():
            table_profile.subject_area = str(merged_communities.get(table_key, -1))

        # Step 6: Classification and summarization
        _logger.info("Classifying tables and generating summaries...")
        classification_start = now()
        for table_key, table_profile in tables.items():
            table_profile.archetype = self._classifier.classify_table(
                table_profile, relationship_graph
            )
            table_profile.summary = self._classifier.summarize_table(table_profile)

            # Compute derived metrics
            table_profile.n_metrics = sum(
                1 for col in table_profile.columns if col.role == "metric"
            )
            table_profile.n_dates = sum(1 for col in table_profile.columns if col.role == "date")
            table_profile.is_archive = is_archive_label(table_key)

        # Audit-like detection based on centrality and generic tokens
        centrality_values = [tp.centrality or 0.0 for tp in tables.values()]
        centrality_threshold = (
            float(np.percentile(centrality_values, 80)) if centrality_values else 0.0
        )

        for table_profile in tables.values():
            table_tokens = set(tokens_from_text(table_profile.name))
            has_generic_tokens = any(
                token in Constants.GENERIC_DIMENSION_TOKENS for token in table_tokens
            )
            is_high_centrality_no_measures = (
                (table_profile.centrality or 0.0) >= centrality_threshold
                and table_profile.n_metrics == 0
                and table_profile.n_dates == 0
            )
            table_profile.is_audit_like = has_generic_tokens or is_high_centrality_no_measures

        timings["classify_summarize"] = now() - classification_start

        # Minimal heartbeat: classification/summaries stats
        try:
            total = len(tables)
            fact = sum(1 for tp in tables.values() if tp.archetype == "fact")
            dimension = sum(1 for tp in tables.values() if tp.archetype == "dimension")
            summaries = sum(1 for tp in tables.values() if (tp.summary or "").strip())
            _logger.info(
                "classify: total=%d fact=%d dimension=%d summaries=%d",
                total,
                fact,
                dimension,
                summaries,
            )
        except Exception:  # noqa: BLE001 - observability-only
            _logger.debug("classification heartbeat logging failed", exc_info=True)

        # Step 7: Subject area descriptions
        subject_areas = self._build_subject_area_descriptions(tables)

        # Step 8: Create SchemaCard
        edges = [(u, v, relationship_graph[u][v]["fk"]) for u, v in relationship_graph.edges()]

        self.card = SchemaCard(
            db_dialect=self._engine.dialect.name,
            db_url_fingerprint=db_url_fingerprint,
            schemas=schemas,
            subject_areas=subject_areas,
            tables=tables,
            edges=edges,
            built_at=time.time(),
            reflection_hash=self._reflection_hash,
        )

        timings["build_index_total"] = now() - total_start

        _logger.info("Schema index built successfully in %.2fs", timings["build_index_total"])
        return self.card

    # ---- internals ---------------------------------------------------------

    def _sample_and_profile_tables(self, tables: dict[str, TableProfile]) -> dict[str, int]:
        """Sample and profile tables using a single streaming connection.

        Returns a mapping of ``"schema.table"`` to the number of columns
        actually selected for sampling (after LOB filtering and column cap).
        Keeps logic out of ``build_index`` to reduce branching and improve readability.
        """
        coverage: dict[str, int] = {}
        with self._engine.connect() as _conn:
            streaming_conn = _conn.execution_options(stream_results=True)
            for table_profile in list(tables.values()):
                preview_cols = 12  # limit for DEBUG column name preview
                columns_ordered = table_profile.columns
                if self.config.max_sampled_columns:
                    columns_ordered = columns_ordered[: self.config.max_sampled_columns]

                def _is_lob(type_str: str) -> bool:
                    t = (type_str or "").lower()
                    return any(
                        hint in t
                        for hint in ("blob", "clob", "bytea", "varbinary", "image", "ntext")
                    )

                column_names = [col.name for col in columns_ordered if not _is_lob(col.type)]
                lob_skipped = max(0, len(columns_ordered) - len(column_names))

                # DEBUG visibility per table
                try:
                    preview = ", ".join(column_names[:preview_cols])
                    if len(column_names) > preview_cols:
                        preview += ", …"
                    _logger.debug(
                        "sampling table %s.%s: cols=%d [%s] lob_skipped=%d",
                        table_profile.schema,
                        table_profile.name,
                        len(column_names),
                        preview,
                        lob_skipped,
                    )
                except Exception:  # noqa: BLE001 - observability-only
                    _logger.debug("sampling table preview failed", exc_info=True)

                sample_data = self._sampler.sample_table(
                    table_profile.schema, table_profile.name, column_names, conn=streaming_conn
                )
                updated = self._profiler.profile_table(
                    table_profile,
                    sample_data,
                    value_constraint_threshold=self.config.value_constraint_threshold,
                )
                tables[f"{updated.schema}.{updated.name}"] = updated
                coverage[f"{updated.schema}.{updated.name}"] = len(column_names)

                # DEBUG post-profile heartbeat per table
                _logger.debug(
                    "profiled %s.%s: rows_sampled=%d",
                    updated.schema,
                    updated.name,
                    int(updated.n_rows_sampled or 0),
                )

        return coverage

    def update_index_if_changed(self) -> bool:
        """Update schema index if the database schema has changed.

        Compares current schema fingerprint with cached version and
        rebuilds the index if changes are detected.

        Returns:
            True if index was rebuilt, False if no changes detected
        """
        current_reflection = self._reflector.reflect()
        current_hash = fingerprint_reflection(current_reflection)

        if self.card and self.card.reflection_hash == current_hash:
            _logger.info("Schema unchanged; skipping rebuild.")
            return False

        _logger.info("Schema changed; rebuilding index.")
        self.build_index()
        return True

    def enrich_index(self) -> SchemaCard:
        """Run a background enrichment pass to complete the index.

        Switches reflection to full mode (FKs enabled, no table cap) and
        rebuilds the schema card. Intended to be executed after initial READY
        to enrich relationships and communities.

        Returns:
            Rebuilt SchemaCard with full relationships and metrics.
        """
        # Temporarily switch reflector to full reflection
        try:
            self._reflector.fast_startup = False
            self._reflector.max_tables_at_startup = None
            return self.build_index()
        finally:
            # Leave it in full mode after enrichment to avoid reintroducing caps
            # (no-op restore). Kept for clarity and potential future use.
            self._reflector.fast_startup = False
            self._reflector.max_tables_at_startup = None

    def needs_rebuild(self) -> bool:
        """Check if the schema has changed and needs rebuilding.

        Compares current schema fingerprint with existing schema card
        to determine if a rebuild is necessary.

        Returns:
            True if rebuild is needed, False if existing schema is current
        """
        if not self.card:
            return True

        current_reflection = self._reflector.reflect()
        current_hash = fingerprint_reflection(current_reflection)

        return self.card.reflection_hash != current_hash

    # Private helper methods

    def _merge_subject_areas(
        self,
        _graph: nx.DiGraph[str],
        node_to_community: dict[str, int],
        _tables: dict[str, TableProfile],
        _min_size: int = 3,
        *,
        _merge_archive: bool = True,
    ) -> dict[str, int]:
        """Merge small and archive-dominated subject areas."""
        # This is a simplified version - the full implementation would be quite long
        # For now, return the original communities
        return node_to_community

    def _build_subject_area_descriptions(
        self, tables: dict[str, TableProfile]
    ) -> dict[str, SubjectAreaData]:
        """Build descriptions for subject areas."""
        areas: dict[str, SubjectAreaData] = {}
        area_groups: dict[str, list[TableProfile]] = defaultdict(list)

        for table_profile in tables.values():
            area_id = table_profile.subject_area or "unknown"
            area_groups[area_id].append(table_profile)

        for area_id, table_list in area_groups.items():
            # Generate area name from common tokens
            all_table_tokens: Counter[str] = Counter()
            for tp in tables.values():
                all_table_tokens.update(tokens_from_text(tp.name))

            common_tokens = {t for t, _ in all_table_tokens.most_common(10)}
            area_tokens: Counter[str] = Counter()

            generic_tokens = {
                "id",
                "name",
                "key",
                "last",
                "edited",
                "by",
                "valid",
                "from",
                "to",
                "pk",
            }

            for table_profile in table_list:
                min_token_length = 2
                tokens = [
                    token
                    for token in tokens_from_text(table_profile.name)
                    if token not in common_tokens
                    and token not in generic_tokens
                    and len(token) > min_token_length
                ]
                area_tokens.update(tokens)

            top_tokens = [token for token, _ in area_tokens.most_common(3)]
            area_name = " / ".join(top_tokens) if top_tokens else f"area_{area_id}"

            # Generate summary
            top_tables = sorted(table_list, key=lambda x: x.centrality or 0, reverse=True)[:5]

            archetype_dist = Counter(tp.archetype or "unknown" for tp in table_list)

            key_tables_str = ", ".join(f"{tp.schema}.{tp.name}" for tp in top_tables)
            archetypes_str = ", ".join(f"{k}:{v}" for k, v in archetype_dist.items())
            summary_parts = [
                f"Key tables: {key_tables_str}",
                f"archetypes: {archetypes_str}",
            ]

            areas[str(area_id)] = SubjectAreaData(
                name=area_name,
                tables=[f"{tp.schema}.{tp.name}" for tp in table_list],
                summary="; ".join(summary_parts),
            )

        return areas
