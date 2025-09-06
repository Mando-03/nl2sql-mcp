"""Embedding functionality for semantic search and analysis.

This module provides embedding capabilities for semantic similarity search over
database schema elements. It includes a light wrapper over ``model2vec``
(`StaticModel`) for fast CPU-only sentence embeddings, an Annoy-backed semantic
index, and a token-lexicon learner used for query expansion.

Classes:
- Embedder: Wrapper for Model2Vec ``StaticModel`` embedding models
- SemanticIndex: Annoy-backed semantic similarity index
- TokenLexiconLearner: Learns token embeddings for query expansion
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Protocol, cast, runtime_checkable

from annoy import AnnoyIndex
from fastmcp.utilities.logging import get_logger
from model2vec import StaticModel
import numpy as np

from .utils import tokens_from_text

# Logger
_logger = get_logger("schema_explorer.embeddings")


@runtime_checkable
class _EmbeddingBackend(Protocol):
    """Protocol for embedding backends.

    Any embedding backend must implement an ``encode`` method compatible with
    Model2Vec's interface, returning a 2D NumPy array of dtype ``float32``.
    """

    def encode(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - protocol
        ...


class Embedder:
    """Wrapper for Model2Vec static embedding models.

    This class provides a consistent interface for text embeddings using
    Model2Vec's CPU-optimized ``StaticModel`` loaded from the Hugging Face Hub.

    Attributes:
        _backend: Concrete embedding backend implementing ``_EmbeddingBackend``
    """

    def __init__(self, model_name: str = "minishlab/potion-retrieval-8M") -> None:
        """Initialize the embedder with a Model2Vec model.

        Args:
            model_name: Name or path of the Model2Vec model to load. Defaults to
                ``minishlab/potion-retrieval-8M``.

        Raises:
            RuntimeError: If ``model2vec`` is not installed or fails to load.
        """
        backend = StaticModel.from_pretrained(model_name)
        # Cast to the minimal protocol to keep strict typing without relying on
        # third-party type hints.
        self._backend: _EmbeddingBackend = cast(_EmbeddingBackend, backend)
        _logger.info("Embedding backend: model2vec model=%s", model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts into embedding vectors.

        Args:
            texts: List of text strings to encode

        Returns:
            NumPy array of embedding vectors with shape ``(len(texts), dim)`` and
            dtype ``float32``.
        """
        # Model2Vec performs its own internal batching; return float32 for ANN.
        vecs = self._backend.encode(list(texts))
        if vecs.dtype != np.float32:
            vecs = vecs.astype("float32", copy=False)
        return vecs


class SemanticIndex:
    """Annoy-backed semantic similarity index for fast vector search.

    This class provides efficient similarity search over embedding vectors
    using Annoy for approximate nearest neighbor search.

    Attributes:
        labels: List of labels corresponding to indexed vectors
        vecs: NumPy array of embedding vectors
        index: Annoy index for fast similarity search
    """

    def __init__(self) -> None:
        """Initialize an empty semantic index."""
        self.labels: list[str] = []
        self.vecs: np.ndarray | None = None
        self.index: AnnoyIndex | None = None

    def build(self, labels: list[str], vectors: np.ndarray) -> None:
        """Build the semantic index from labels and vectors.

        Args:
            labels: List of string labels for the vectors
            vectors: NumPy array of embedding vectors
        """
        self.labels = labels
        self.vecs = vectors

        if vectors.shape[0] > 0:
            # Build Annoy index for fast similarity search
            embedding_dim = vectors.shape[1]
            self.index = AnnoyIndex(embedding_dim, "angular")  # angular = cosine distance

            # Add normalized vectors to index
            normalized_vectors = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-8)
            for i, vector in enumerate(normalized_vectors):
                self.index.add_item(i, vector.tolist())

            # Build the index with 10 trees (good balance of speed/accuracy)
            self.index.build(10)
        else:
            self.index = None

    def search(self, query_vector: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        """Search for most similar vectors in the index.

        Args:
            query_vector: Query embedding vector
            k: Number of top results to return

        Returns:
            List of (label, similarity_score) tuples, sorted by similarity
        """
        if self.vecs is None or len(self.vecs) == 0 or self.index is None:
            return []

        # Normalize query vector
        query_normalized = query_vector / (np.linalg.norm(query_vector) + 1e-8)

        # Use Annoy for fast search
        indices, distances = self.index.get_nns_by_vector(
            query_normalized.tolist(), k, include_distances=True
        )
        results: list[tuple[str, float]] = []
        for idx, dist in zip(indices, distances, strict=False):
            # Convert angular distance back to cosine similarity
            # Formula is: cos_sim = 1 - (angular_dist^2 / 2)
            similarity = 1.0 - (dist * dist / 2.0)
            results.append((self.labels[idx], similarity))
        return results


class TokenLexiconLearner:
    """Learns token embeddings from schema elements for query expansion.

    This class builds a lexicon of tokens extracted from table and column names,
    creating embeddings for each token based on the contexts where it appears.
    It enables semantic expansion of query terms with related schema tokens.

    Attributes:
        token_to_items: Maps tokens to lists of item indices where they appear
        token_df: Document frequency count for each token
        tokens: Sorted list of unique tokens
        vecs: Embedding vectors for tokens
        index: Semantic index for token similarity search
    """

    def __init__(self) -> None:
        """Initialize an empty token lexicon learner."""
        self.token_to_items: dict[str, list[int]] = defaultdict(list)
        self.token_df: dict[str, int] = {}
        self.tokens: list[str] = []
        self.vecs: np.ndarray | None = None
        self.index = SemanticIndex()
        self._built = False

    def build(self, item_labels: list[str], item_vectors: np.ndarray) -> None:
        """Build token embeddings from item labels and their vectors.

        Extracts tokens from item labels (table/column names), computes
        document frequencies, and creates token embeddings by averaging
        the vectors of items containing each token.

        Args:
            item_labels: List of item labels (table or column identifiers)
            item_vectors: Corresponding embedding vectors for items
        """
        # Extract tokens from each label
        label_tokens: list[list[str]] = []
        for label in item_labels:
            if "::" in label:
                # Column label format: "schema.table::column"
                table_part, column_part = label.split("::", 1)
                schema, table = table_part.split(".", 1)
                tokens = tokens_from_text(table) + tokens_from_text(column_part)
            else:
                # Table label format: "schema.table"
                schema, table = label.split(".", 1)
                tokens = tokens_from_text(table) + tokens_from_text(schema)

            # Filter out numeric tokens and deduplicate
            filtered_tokens = [token for token in tokens if token and not token.isdigit()]
            label_tokens.append(list(dict.fromkeys(filtered_tokens)))

        # Build token-to-items mapping and document frequency
        df_counter: Counter[str] = Counter()
        for item_index, tokens in enumerate(label_tokens):
            for token in tokens:
                self.token_to_items[token].append(item_index)
            df_counter.update(tokens)

        self.token_df = dict(df_counter)

        # Sort tokens by document frequency (descending) then alphabetically
        tokens_sorted = sorted(
            self.token_to_items.keys(), key=lambda token: (-self.token_df[token], token)
        )

        # Compute token embeddings by averaging item vectors
        token_embeddings = []
        for token in tokens_sorted:
            item_indices = self.token_to_items[token]
            if not item_indices:
                continue

            # Average vectors of all items containing this token
            token_embedding = item_vectors[item_indices].mean(axis=0)  # type: ignore[misc]
            token_embeddings.append(token_embedding)

        self.tokens = tokens_sorted
        self.vecs = (
            np.vstack(token_embeddings)  # type: ignore[misc]
            if token_embeddings
            else np.zeros((0, item_vectors.shape[1]), dtype="float32")
        )

        # Build semantic index for token similarity search
        if len(self.tokens) > 0:
            token_labels = [f"tok::{token}" for token in self.tokens]
            self.index.build(token_labels, self.vecs)  # type: ignore[misc]

        self._built = True

    def expand_tokens_by_query(
        self,
        query_vector: np.ndarray,
        top_n: int = 10,
        min_df: int = 2,
        exclude: list[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Find tokens semantically similar to a query vector.

        Searches for tokens that are semantically similar to the query
        and have sufficient document frequency for meaningful expansion.

        Args:
            query_vector: Query embedding vector
            top_n: Maximum number of tokens to return
            min_df: Minimum document frequency threshold
            exclude: List of tokens to exclude from results

        Returns:
            List of (token, similarity_score) tuples for expansion
        """
        if not self._built or len(self.tokens) == 0:
            return []

        # Search for similar tokens
        candidate_count = min(top_n * 5, len(self.tokens))
        hits = self.index.search(query_vector, k=candidate_count)

        exclude_set = set(exclude or [])
        results: list[tuple[str, float]] = []

        for label, score in hits:
            # Extract token from label (format: "tok::token")
            token = label.split("::", 1)[-1]

            if token in exclude_set:
                continue

            # Check document frequency threshold
            if self.token_df.get(token, 0) >= min_df:
                results.append((token, float(score)))

            if len(results) >= top_n:
                break

        return results
