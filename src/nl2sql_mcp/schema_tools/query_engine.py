"""Query engine for processing natural language queries against schema cards.

This module contains the QueryEngine class that handles query-time operations
including table retrieval, graph expansion, and SQL prompt generation.
It operates on pre-built schema cards and provides focused functionality
for natural language to SQL generation.

Classes:
- QueryEngine: Main query processor for schema cards
"""

from __future__ import annotations

from collections import defaultdict

from fastmcp.utilities.logging import get_logger
import numpy as np

from .embeddings import Embedder, SemanticIndex, TokenLexiconLearner
from .expansion import GraphExpander
from .models import SchemaCard, SchemaExplorerConfig
from .retrieval import RetrievalEngine
from .utils import is_archive_label, tokens_from_text

# Logger
_logger = get_logger("query_engine")


class QueryEngine:
    """Query engine for processing natural language queries against schema cards.

    This class handles all query-time operations including table retrieval,
    graph expansion, and SQL prompt generation. It operates on pre-built
    schema cards and provides focused functionality separate from schema
    building and analysis.

    Attributes:
        schema_card: Pre-built schema card with analyzed metadata
        config: Configuration object containing settings
        embedder: Optional embedder for semantic similarity
        retrieval_engine: Engine for query-driven table retrieval
        graph_expander: Graph expansion algorithms
    """

    def __init__(
        self,
        schema_card: SchemaCard,
        config: SchemaExplorerConfig,
        embedder: Embedder | None = None,
    ) -> None:
        """Initialize the QueryEngine.

        Args:
            schema_card: Pre-built schema card with analyzed metadata
            config: Configuration object containing settings
            embedder: Optional embedder for semantic similarity
        """
        self.schema_card = schema_card
        self.config = config
        self.embedder = embedder

        # Initialize embedder if not provided. Fail-soft to lexical-only when
        # the embedding backend cannot be created.
        if not self.embedder:
            try:
                self.embedder = Embedder(model_name=config.model_name)
                _logger.info("Initialized embedder with model: %s", config.model_name)
            except (RuntimeError, OSError, FileNotFoundError, ValueError) as e:
                _logger.warning("Embeddings disabled due to initialization error: %s", e)
                self.embedder = None

        # Component instances
        self.retrieval_engine: RetrievalEngine | None = None
        self.graph_expander: GraphExpander | None = None

        # Embedding indices
        self.table_index: SemanticIndex | None = None
        self.column_index: SemanticIndex | None = None
        self.lexicon_learner = TokenLexiconLearner()

        # Cached data for retrieval
        self._table_labels: list[str] = []
        self._table_vecs: np.ndarray | None = None
        self._col_labels: list[str] = []
        self._col_vecs: np.ndarray | None = None
        self._lexical_cache: dict[str, dict[str, float]] = {}

        # Initialize components
        self._initialize_components()

    def _initialize_components(self) -> None:
        """Initialize retrieval and expansion components."""
        # Build lexical cache
        self._build_lexical_cache()

        # Build embeddings if embedder available
        if self.embedder:
            self._build_table_embeddings()
            if self.config.build_column_index:
                self._build_column_embeddings()

            # Build token lexicon
            if self._col_labels and self._col_vecs is not None and len(self._col_labels) > 0:
                self.lexicon_learner.build(self._col_labels, self._col_vecs)
            elif self._table_vecs is not None:
                self.lexicon_learner.build(self._table_labels, self._table_vecs)

        # Initialize retrieval and expansion engines
        self.retrieval_engine = RetrievalEngine(
            schema_card=self.schema_card,
            embedder=self.embedder,
            table_index=self.table_index,
            column_index=self.column_index,
            lexicon_learner=self.lexicon_learner,
            lexical_cache=self._lexical_cache,
            exclude_archives=self.config.strict_archive_exclude,
            lexicon_top_n=self.config.lexicon_top_n,
            lexicon_min_df=self.config.lexicon_min_df,
            morph_min_len=self.config.morph_min_len,
        )

        self.graph_expander = GraphExpander(
            schema_card=self.schema_card,
            expander_type=self.config.expander,
        )

    def _build_lexical_cache(self) -> None:
        """Build lexical token cache for tables."""

        self._lexical_cache = {}

        for table_key, table_profile in self.schema_card.tables.items():
            token_weights: dict[str, float] = defaultdict(float)

            # Add table name tokens
            for token in tokens_from_text(table_profile.name):
                token_weights[token] += 2.0

            # Add schema name tokens
            for token in tokens_from_text(table_profile.schema):
                token_weights[token] += 0.5

            # Add column name and role tokens
            for column in table_profile.columns:
                for token in tokens_from_text(column.name):
                    token_weights[token] += 1.0

                if column.role:
                    for token in tokens_from_text(column.role):
                        token_weights[token] += 0.5

            # Downweight archive tables
            if is_archive_label(table_key):
                for token in list(token_weights.keys()):
                    token_weights[token] *= 0.2

            self._lexical_cache[table_key] = dict(token_weights)

    def _build_table_embeddings(self) -> None:
        """Build table-level embeddings."""
        if not self.embedder:
            return

        labels: list[str] = []
        texts: list[str] = []

        for table_key, table_profile in self.schema_card.tables.items():
            # Create rich text description
            column_descriptions: list[str] = []
            for col in table_profile.columns[:12]:  # Limit columns for token efficiency
                role_part = col.role or ""
                fk_part = f" -> {col.fk_ref[0]}" if col.is_fk and col.fk_ref else ""
                column_descriptions.append(f"{col.name}({role_part}){fk_part}")

            columns_str = ", ".join(column_descriptions)
            table_name = f"{table_profile.schema}.{table_profile.name}"
            text = f"{table_name}: {table_profile.summary}. Columns: {columns_str}"

            labels.append(table_key)
            texts.append(text)

        # Generate embeddings
        embeddings = self.embedder.encode(texts)

        # Store for retrieval engine
        self._table_labels = labels
        self._table_vecs = embeddings

        # Build semantic index
        self.table_index = SemanticIndex()
        self.table_index.build(labels, embeddings)

        # Minimal heartbeat: table embeddings stats
        try:
            count = len(labels)
            dim = int(embeddings.shape[1]) if embeddings.size > 0 else 0
            _logger.info("embeddings.tables: count=%d dim=%d", count, dim)
        except Exception:  # noqa: BLE001 - observability-only
            _logger.debug("table embeddings heartbeat logging failed", exc_info=True)

    def _build_column_embeddings(self) -> None:
        """Build column-level embeddings."""
        if not self.embedder:
            return

        labels: list[str] = []
        texts: list[str] = []

        for table_key, table_profile in self.schema_card.tables.items():
            for col in table_profile.columns[: self.config.max_cols_for_embeddings]:
                fk_info = f" -> {col.fk_ref[0]}" if col.is_fk and col.fk_ref else ""
                col_name = f"{table_profile.schema}.{table_profile.name}.{col.name}"
                tags_str = ",".join(col.semantic_tags)
                text = (
                    f"{col_name}: "
                    f"role={col.role}; type={col.type}; tags={tags_str}"
                    f"{fk_info}; table={table_profile.summary}"
                )

                labels.append(f"{table_key}::{col.name}")
                texts.append(text)

        if texts:
            embeddings = self.embedder.encode(texts)
        elif self._table_vecs is not None:
            # Create empty array with same dimension as table embeddings
            embeddings = np.zeros((0, self._table_vecs.shape[1]), dtype="float32")
        else:
            # Default embedding dimension
            embeddings = np.zeros((0, 384), dtype="float32")

        # Store for retrieval engine
        self._col_labels = labels
        self._col_vecs = embeddings

        # Build semantic index
        if len(labels) > 0:
            self.column_index = SemanticIndex()
            self.column_index.build(labels, embeddings)

        # Minimal heartbeat: column embeddings stats (only when index/vecs prepared)
        try:
            count = len(labels)
            dim = int(embeddings.shape[1]) if embeddings.size > 0 else 0
            _logger.info("embeddings.columns: count=%d dim=%d", count, dim)
        except Exception:  # noqa: BLE001 - observability-only
            _logger.debug("column embeddings heartbeat logging failed", exc_info=True)
