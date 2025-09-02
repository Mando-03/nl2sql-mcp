"""Utility functions for schema exploration.

This module contains utility functions used throughout the schema exploration
system. These functions provide common operations like text normalization,
tokenization, fingerprinting, and database dialect-specific configurations.

Functions:
- normalize_identifier(): Convert database identifiers to normalized tokens
- tokens_from_text(): Extract normalized tokens from text
- fingerprint_reflection(): Generate deterministic hash of reflection data
- default_excluded_schemas(): Get system schemas to exclude by dialect
- is_archive_label(): Detect archive/historical data indicators
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from fastmcp.utilities.logging import get_logger

from .constants import Constants

# Logger setup
_logger = get_logger("schema_explorer")


def now() -> float:
    """Return high-resolution timestamp for performance measurements.

    Returns:
        Current time in seconds since epoch with high precision
    """
    return time.perf_counter()


def normalize_identifier(name: str) -> str:
    """Normalize database identifiers to lowercase space-separated tokens.

    Converts CamelCase and snake_case identifiers to space-separated lowercase
    tokens for consistent text processing and matching.

    Args:
        name: Database identifier (table/column name)

    Returns:
        Normalized lowercase string with spaces between tokens

    Example:
        >>> normalize_identifier("customer_orders")
        'customer orders'
        >>> normalize_identifier("CustomerOrders")
        'customer orders'
        >>> normalize_identifier("XMLHttpRequest")
        'xmlhttprequest'
    """
    if not name:
        return ""

    # Replace underscores and dashes with spaces
    normalized = re.sub(r"[_\-]+", " ", name)

    # Insert spaces before capital letters (for CamelCase)
    normalized = re.sub(r"(?<!^)(?=[A-Z])", " ", normalized)

    # Collapse multiple spaces and convert to lowercase
    return re.sub(r"\s+", " ", normalized).strip().lower()


def tokens_from_text(text: str) -> list[str]:
    """Extract normalized tokens from text.

    Converts text to normalized identifier format and extracts
    alphanumeric tokens, filtering out empty strings and non-meaningful tokens.

    Args:
        text: Input text to tokenize

    Returns:
        List of lowercase alphanumeric tokens
    """
    normalized_text = normalize_identifier(text or "")
    return [token for token in re.split(r"[^a-z0-9]+", normalized_text) if token]


def fingerprint_reflection(payload: dict[str, Any]) -> str:
    """Generate deterministic hash fingerprint of reflection payload.

    Creates a consistent hash of database reflection data that can be used
    to detect schema changes and avoid unnecessary re-processing.

    Args:
        payload: Database schema reflection data dictionary

    Returns:
        16-character hex hash string representing the payload
    """
    # Convert to JSON with consistent key ordering
    json_string = json.dumps(payload, sort_keys=True, default=str)

    # Generate SHA-256 hash and return first 16 characters
    return hashlib.sha256(json_string.encode("utf-8")).hexdigest()[:16]


def default_excluded_schemas(dialect_name: str) -> list[str]:
    """Get default system schemas to exclude for a database dialect.

    Returns a list of system schema names that should typically be excluded
    from schema analysis for the given database dialect.

    Args:
        dialect_name: SQLAlchemy dialect name (e.g., 'postgresql', 'mysql')

    Returns:
        List of system schema names to exclude from analysis
    """
    dialect_lower = dialect_name.lower()

    if "postgresql" in dialect_lower or "postgres" in dialect_lower:
        return ["information_schema", "pg_catalog", "pg_toast"]
    if "mssql" in dialect_lower or "sqlserver" in dialect_lower:
        return ["information_schema", "sys"]
    if "mysql" in dialect_lower:
        return ["information_schema", "mysql", "performance_schema", "sys"]
    if "oracle" in dialect_lower:
        return ["sys", "system", "xdb", "mdsys", "ctxsys"]
    if "snowflake" in dialect_lower:
        return ["information_schema"]
    # Default fallback for unknown dialects
    return ["information_schema", "pg_catalog", "sys"]


def is_archive_label(label: str) -> bool:
    """Check if a table/column label indicates archive/historical data.

    Uses pattern matching to detect table or column names that suggest
    archival or historical data storage.

    Args:
        label: Either "schema.table" or "schema.table::column" format

    Returns:
        True if the label appears to indicate archive/historical data
    """
    # Extract the table name from the label
    table_part = label.split("::")[0].split(".")[-1]
    return bool(Constants.ARCHIVE_PATTERN.search(table_part))
