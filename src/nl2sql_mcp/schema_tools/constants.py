"""Constants and enums for SchemaExplorer.

This module contains all configuration constants, regex patterns,
and enumeration definitions used throughout the schema exploration system.
"""

from __future__ import annotations

from enum import Enum
import re
from typing import Final


class Constants:
    """Configuration constants for SchemaExplorer."""

    # Defaults
    DEFAULT_SAMPLE_ROWS: Final[int] = 100
    DEFAULT_TIMEOUT_SEC: Final[int] = 5
    DEFAULT_TOP_K_TABLES: Final[int] = 8
    DEFAULT_MIN_AREA_SIZE: Final[int] = 3
    DEFAULT_EMBEDDING_MODEL: Final[str] = "minishlab/potion-retrieval-8M"
    DEFAULT_MAX_COLS_FOR_EMBEDDINGS: Final[int] = 20
    DEFAULT_VALUE_CONSTRAINT_THRESHOLD: Final[int] = 20

    # Regex patterns
    EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    PHONE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\+?\d[\d\-\s]{7,}\d$")
    URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^https?://")
    PERCENT_PATTERN: Final[re.Pattern[str]] = re.compile(r"%$")
    ARCHIVE_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"(archive|archived|hist|history|backup|bak|old|tmp|temp)$", re.IGNORECASE
    )

    # Semantic hints for type detection
    DATE_TYPE_HINTS: Final[frozenset[str]] = frozenset({"date", "datetime", "time", "timestamp"})
    NUMERIC_TYPE_HINTS: Final[frozenset[str]] = frozenset(
        {"int", "dec", "num", "float", "double", "real"}
    )

    # Generic dimension tokens for audit-like detection
    GENERIC_DIMENSION_TOKENS: Final[frozenset[str]] = frozenset(
        {
            "people",
            "person",
            "user",
            "users",
            "transaction",
            "transactions",
            "transactiontype",
            "transactiontypes",
            "type",
            "types",
            "status",
            "statuses",
            "method",
            "methods",
            "parameter",
            "parameters",
            "system",
            "systems",
            "sys",
            "log",
            "logs",
            "history",
            "archive",
            "archived",
            "temp",
            "tmp",
            "code",
            "codes",
            "lookup",
            "lookups",
            "ref",
            "reference",
            "references",
        }
    )


class ColumnRole(Enum):
    """Semantic roles for database columns."""

    KEY = "key"  # Primary keys, foreign keys, identifiers
    DATE = "date"  # Date, datetime, timestamp columns
    METRIC = "metric"  # Numeric measures, facts, quantities
    CATEGORY = "category"  # Categorical dimensions, classifications
    TEXT = "text"  # Free-form text content
    ID = "id"  # Identifier columns


class TableArchetype(Enum):
    """High-level table classifications in dimensional modeling."""

    FACT = "fact"  # Central transactional tables with measures
    DIMENSION = "dimension"  # Lookup tables with descriptive attributes
    BRIDGE = "bridge"  # Many-to-many relationship tables
    REFERENCE = "reference"  # Static lookup/code tables
    OPERATIONAL = "operational"  # General operational tables


class RetrievalApproach(Enum):
    """Different approaches for table retrieval."""

    LEXICAL = "lexical"  # Token-based matching
    EMBEDDING_TABLE = "emb_table"  # Table-level embeddings
    EMBEDDING_COLUMN = "emb_column"  # Column-level embeddings
    COMBINED = "combo"  # Hybrid approach


# Legacy constants for backward compatibility
GENERIC_DIM_TOKENS = Constants.GENERIC_DIMENSION_TOKENS

__all__ = [
    "GENERIC_DIM_TOKENS",  # Legacy export
    "ColumnRole",
    "Constants",
    "RetrievalApproach",
    "TableArchetype",
]
