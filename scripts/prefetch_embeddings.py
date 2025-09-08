"""Prefetch and cache the default embeddings model.

This build-time script downloads the embedding assets used by nl2sql-mcp to
reduce server startup latency. It intentionally avoids importing the
``nl2sql_mcp`` package to prevent optional runtime dependencies (e.g.,
``pyodbc``) from being imported during the image build.

Behavior:
- Respects ``NL2SQL_MCP_EMBEDDING_MODEL``; falls back to a safe default.
- Uses model2vec's ``StaticModel`` (CPU-only) and triggers a tiny encode to
  fully materialize caches under ``HF_HOME`` or the default HF cache.
"""

from __future__ import annotations

import logging
import os

from model2vec import StaticModel

# Keep the default model here to avoid importing the package during build.
DEFAULT_MODEL = "minishlab/potion-base-8M"


def main() -> None:
    """Download and cache the configured embedding model."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("prefetch_embeddings")

    model_name = os.getenv("NL2SQL_MCP_EMBEDDING_MODEL", DEFAULT_MODEL)
    cache_dir = (
        os.getenv("HF_HOME") or os.getenv("HF_DATASETS_CACHE") or os.getenv("XDG_CACHE_HOME")
    )

    logger.info("Prefetching embedding model: %s", model_name)
    if cache_dir:
        logger.info("Using cache directory: %s", cache_dir)

    model = StaticModel.from_pretrained(model_name)
    # Trigger any lazy initialization; keep it minimal.
    _ = model.encode(["bootstrap"]).shape
    logger.info("Embedding model cached successfully")


if __name__ == "__main__":  # pragma: no cover - build-time utility
    main()
