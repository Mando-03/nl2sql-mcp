"""Table retrieval methods for query-driven schema discovery.

This module provides various approaches for retrieving relevant database tables
based on natural language queries. It includes lexical matching, embedding-based
similarity, and hybrid approaches that combine multiple retrieval strategies.

Classes:
- RetrievalEngine: Main class containing all retrieval methods
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from fastmcp.utilities.logging import get_logger
import numpy as np

from .constants import RetrievalApproach
from .utils import is_archive_label, tokens_from_text

if TYPE_CHECKING:
    from .embeddings import Embedder, SemanticIndex, TokenLexiconLearner
    from .models import SchemaCard

# Logger
_logger = get_logger("schema_explorer.retrieval")


class RetrievalEngine:
    """Engine for retrieving relevant tables based on natural language queries.

    This class provides multiple retrieval approaches including lexical matching,
    embedding-based similarity search, and hybrid methods. It supports both
    static and dynamic lexical expansion using learned token embeddings.

    Attributes:
        schema_card: Complete schema information
        embedder: Optional embedder for semantic similarity
        table_index: Semantic index for table-level embeddings
        column_index: Semantic index for column-level embeddings
        lexicon_learner: Token lexicon for dynamic expansion
        lexical_cache: Pre-computed lexical weights for tables
    """

    def __init__(
        self,
        schema_card: SchemaCard,
        embedder: Embedder | None = None,
        table_index: SemanticIndex | None = None,
        column_index: SemanticIndex | None = None,
        lexicon_learner: TokenLexiconLearner | None = None,
        lexical_cache: dict[str, dict[str, float]] | None = None,
        *,
        exclude_archives: bool = False,
        lexicon_top_n: int = 16,
        lexicon_min_df: int = 2,
        morph_min_len: int = 3,
    ) -> None:
        """Initialize the retrieval engine.

        Args:
            schema_card: Complete schema card with table metadata
            embedder: Optional embedder for semantic similarity
            table_index: Optional semantic index for table embeddings
            column_index: Optional semantic index for column embeddings
            lexicon_learner: Optional token lexicon learner
            lexical_cache: Optional pre-computed lexical weights
        """
        self.schema_card = schema_card
        self.embedder = embedder
        self.table_index = table_index
        self.column_index = column_index
        self.lexicon_learner = lexicon_learner
        self.lexical_cache = lexical_cache or {}

        # Tunable constants for token expansion and priors
        self._MORPH_MIN_LEN: int = max(1, morph_min_len)
        self._LEXICON_TOP_N: int = max(1, lexicon_top_n)
        self._LEXICON_MIN_DF: int = max(1, lexicon_min_df)
        self._EXCLUDE_ARCHIVES: bool = exclude_archives

    def _filter_archive_priority(
        self, items: list[tuple[str, float]], k: int
    ) -> list[tuple[str, float]]:
        """Filter results to prioritize non-archive tables.

        Separates archive and non-archive tables, returning non-archive
        tables first up to the limit, then archive tables if needed.

        Args:
            items: List of (table_key, score) tuples
            k: Maximum number of results to return

        Returns:
            Filtered list prioritizing non-archive tables
        """
        non_archive = [(key, score) for key, score in items if not is_archive_label(key)]
        archive = [(key, score) for key, score in items if is_archive_label(key)]

        if self._EXCLUDE_ARCHIVES and non_archive:
            return non_archive[:k]

        result = non_archive[:k]
        if len(result) < k:
            result.extend(archive[: (k - len(result))])

        return result

    def retrieve_lexical(self, query: str, k: int = 8) -> list[tuple[str, float]]:
        """Retrieve tables using lexical token matching.

        Matches query tokens against pre-computed lexical weights for tables,
        using cosine similarity for scoring.

        Args:
            query: Natural language query
            k: Maximum number of tables to return

        Returns:
            List of (table_key, score) tuples sorted by relevance
        """
        query_tokens = tokens_from_text(query)
        if not query_tokens:
            return []
        # Expand tokens in a data-driven fashion
        q_weights = self._expand_tokens(query_tokens, raw_query=query)

        scores: dict[str, float] = {}
        for table_key, t_weights in self.lexical_cache.items():
            # Compute weighted dot product score between query and table tokens
            score = 0.0
            for token, weight in t_weights.items():
                score += weight * q_weights.get(token, 0.0)

            # Normalize by table's token weight magnitude to reduce bias
            norm = np.sqrt(sum(w * w for w in t_weights.values())) + 1e-8
            scores[table_key] = score / norm

        # Apply learned hint boosts derived from lexical cache
        hints = self._hint_boosts(set(query_tokens))
        for table_key, boost in hints.items():
            if table_key in scores:
                scores[table_key] += boost

        # Sort by score and apply archive filtering
        items = sorted(scores.items(), key=lambda x: -x[1])[: max(k * 3, 50)]
        return self._filter_archive_priority(items, k)

    # --- data-driven expansion helpers ---------------------------------------

    def _expand_tokens(self, tokens: Iterable[str], *, raw_query: str) -> dict[str, float]:
        """Expand query tokens using morphology and schema-learned neighbors.

        - Adds singular/plural variants with reduced weight.
        - If embeddings are available, uses TokenLexiconLearner to fetch
          semantically related schema tokens for the raw query.

        Args:
            tokens: Base tokens extracted from the query
            raw_query: Raw query string for semantic expansion

        Returns:
            A weight map of expanded tokens.
        """
        q_weights: dict[str, float] = defaultdict(float)
        base_tokens: list[str] = [t for t in tokens if t]
        for t in base_tokens:
            q_weights[t] += 1.0

            # Morphology: simple singular/plural variants
            if len(t) >= self._MORPH_MIN_LEN and t.endswith("s"):
                singular = t[:-1]
                if singular and singular != t:
                    q_weights[singular] += 0.3
            elif len(t) >= self._MORPH_MIN_LEN:
                plural = t + "s"
                q_weights[plural] += 0.3

        # Semantic expansion via lexicon learner (if vectors available)
        if self.embedder and (self.table_index or self.column_index) and self.lexicon_learner:
            try:
                qvec = self.embedder.encode([raw_query])[0]
                exclude = list(q_weights.keys())
                neighbors = self.lexicon_learner.expand_tokens_by_query(
                    qvec, top_n=self._LEXICON_TOP_N, min_df=self._LEXICON_MIN_DF, exclude=exclude
                )
                for token, sim in neighbors:
                    # scale by similarity; clamp to reasonable max
                    q_weights[token] += float(max(0.0, min(0.7, 0.7 * sim)))
            except RuntimeError:
                # Embeddings disabled at runtime: skip semantic expansion
                pass

        return dict(q_weights)

    def _hint_boosts(self, tokens: set[str], top_k_per_token: int = 20) -> dict[str, float]:
        """Compute small table-specific boosts from lexical cache.

        For each token, find tables where that token has high lexical weight
        and add a scaled boost. This replaces static table hint lists with
        learned, schema-local priors.

        Args:
            tokens: Set of normalized query tokens
            top_k_per_token: Limit of tables to boost per token

        Returns:
            Mapping of table_key to additive boost.
        """
        boosts: dict[str, float] = defaultdict(float)
        if not tokens:
            return {}

        # For each token, score tables by the token's weight and boost top-K
        for t in tokens:
            per_table: list[tuple[str, float]] = []
            for table_key, t_weights in self.lexical_cache.items():
                w = t_weights.get(t, 0.0)
                if w > 0.0:
                    per_table.append((table_key, w))
            if not per_table:
                continue
            per_table.sort(key=lambda x: -x[1])
            for table_key, w in per_table[:top_k_per_token]:
                # small, bounded boost relative to token weight
                boosts[table_key] += min(0.25, 0.05 + 0.02 * w)

        return dict(boosts)

    def retrieve_table_embeddings(self, query: str, k: int = 8) -> list[tuple[str, float]]:
        """Retrieve tables using table-level embeddings.

        Encodes the query and searches for similar table embeddings using
        the pre-built semantic index.

        Args:
            query: Natural language query
            k: Maximum number of tables to return

        Returns:
            List of (table_key, score) tuples sorted by similarity
        """
        if not self.embedder or not self.table_index:
            return []

        query_vector = self.embedder.encode([query])[0]
        hits = self.table_index.search(query_vector, k=max(k * 3, 50))
        return self._filter_archive_priority(hits, k)

    def retrieve_column_embeddings(
        self, query: str, k_tables: int = 8, k_columns: int = 50
    ) -> list[tuple[str, float]]:
        """Retrieve tables using column-level embeddings.

        Searches column embeddings and aggregates scores by table to find
        tables with the most relevant columns.

        Args:
            query: Natural language query
            k_tables: Maximum number of tables to return
            k_columns: Number of column matches to consider

        Returns:
            List of (table_key, score) tuples sorted by aggregated relevance
        """
        if not self.embedder or not self.column_index:
            return []

        query_vector = self.embedder.encode([query])[0]
        column_hits = self.column_index.search(query_vector, k=k_columns)

        # Aggregate column scores by table
        table_scores: dict[str, float] = defaultdict(float)
        for column_label, score in column_hits:
            table_key = column_label.split("::")[0]
            table_scores[table_key] += max(0.0, score)

        # Sort by aggregated score and apply archive filtering
        items = sorted(table_scores.items(), key=lambda x: -x[1])[: max(k_tables * 3, 50)]
        return self._filter_archive_priority(items, k_tables)

    def retrieve_combined(
        self, query: str, k: int = 8, alpha: float = 0.7
    ) -> list[tuple[str, float]]:
        """Retrieve tables using combined lexical and embedding approaches.

        Combines table embedding similarity with lexical matching using
        a weighted average after score normalization.

        Args:
            query: Natural language query
            k: Maximum number of tables to return
            alpha: Weight for embedding score (1-alpha for lexical)

        Returns:
            List of (table_key, score) tuples with combined scoring
        """
        embedding_results = self.retrieve_table_embeddings(query, k=max(50, k))
        lexical_results = self.retrieve_lexical(query, k=max(50, k))

        def normalize_scores(results: list[tuple[str, float]]) -> dict[str, float]:
            """Normalize scores to [0, 1] range."""
            if not results:
                return {}

            scores = [score for _, score in results]
            min_score, max_score = min(scores), max(scores)
            score_range = (max_score - min_score) + 1e-8

            return {key: (score - min_score) / score_range for key, score in results}

        normalized_embedding = normalize_scores(embedding_results)
        normalized_lexical = normalize_scores(lexical_results)

        # Combine normalized scores
        all_keys = set(normalized_embedding.keys()) | set(normalized_lexical.keys())
        combined_scores = {
            key: alpha * normalized_embedding.get(key, 0.0)
            + (1 - alpha) * normalized_lexical.get(key, 0.0)
            for key in all_keys
        }

        # Optional bias: aggregation/ranking intent prefers tables with metrics/dates
        # Use expanded token set for lexical overlap bonus to capture
        # schema-learned synonyms (e.g., shipping -> delivery)
        raw_tokens = list(tokens_from_text(query))
        expanded_map = self._expand_tokens(raw_tokens, raw_query=query)
        query_tokens = set(expanded_map.keys())
        agg_signals = {
            "top",
            "rank",
            "ranked",
            "sum",
            "total",
            "count",
            "avg",
            "average",
            "median",
            "percent",
            "percentage",
        }
        has_agg_intent = bool(agg_signals & query_tokens)

        if has_agg_intent:
            for key in list(combined_scores.keys()):
                tp = self.schema_card.tables.get(key)
                if tp:
                    bonus = 0.0
                    if tp.n_metrics > 0:
                        bonus += 0.08
                    if tp.n_dates > 0:
                        bonus += 0.04
                    # Slightly prefer fact archetypes
                    if tp.archetype and tp.archetype.lower() == "fact":
                        bonus += 0.06
                    combined_scores[key] += bonus

        # New: lexical overlap bonus between query tokens and table lexical cache
        if query_tokens:
            for key in list(combined_scores.keys()):
                tlex = self.lexical_cache.get(key, {})
                overlap = sum(tlex.get(t, 0.0) for t in query_tokens)
                # scale small to avoid dominating; normalize by sqrt of token mass
                norm = (sum(w * w for w in tlex.values()) ** 0.5) + 1e-8
                combined_scores[key] += 0.12 * (overlap / norm)

        # Sort and apply archive filtering
        items = sorted(combined_scores.items(), key=lambda x: -x[1])[: max(50, k)]
        return self._filter_archive_priority(items, k)

    def retrieve(
        self, query: str, approach: RetrievalApproach, k: int = 8
    ) -> list[tuple[str, float]]:
        """Retrieve tables using the specified approach.

        Args:
            query: Natural language query
            approach: Retrieval approach to use
            k: Maximum number of tables to return

        Returns:
            List of (table_key, score) tuples sorted by relevance
        """
        if approach == RetrievalApproach.LEXICAL:
            return self.retrieve_lexical(query, k)
        if approach == RetrievalApproach.EMBEDDING_TABLE:
            return self.retrieve_table_embeddings(query, k)
        if approach == RetrievalApproach.EMBEDDING_COLUMN:
            return self.retrieve_column_embeddings(query, k_tables=k)
        return self.retrieve_combined(query, k)
