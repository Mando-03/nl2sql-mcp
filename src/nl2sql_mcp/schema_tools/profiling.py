"""Column profiling and semantic analysis.

This module provides the Profiler class that analyzes sampled table data
to infer column roles, detect semantic patterns, and extract metadata.
It includes pattern recognition for common data types like emails, phones,
URLs, and uses NLP techniques when available for entity detection.

Classes:
- Profiler: Main class for column profiling and semantic analysis
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fastmcp.utilities.logging import get_logger
import pandas as pd

from .constants import Constants
from .lightweight_ner import LightweightNER
from .utils import normalize_identifier

if TYPE_CHECKING:
    from .models import TableProfile

MIN_UNIQUE_COUNT_FOR_METRIC = 10

# Logger
_logger = get_logger("schema_explorer.profiling")

# Lightweight NER backed by authoritative sources
_ner_instance = LightweightNER()


class Profiler:
    """Column profiler for semantic analysis and role detection.

    This class analyzes sampled table data to infer semantic information
    about columns, including data types, patterns, and roles within the
    data model. It uses pattern matching and optional NLP techniques
    to provide rich metadata for query generation.

    Attributes:
        nlp: Optional lightweight NER pipeline for entity recognition
        EMAIL_RE: Compiled regex for email pattern detection
        PHONE_RE: Compiled regex for phone number pattern detection
        URL_RE: Compiled regex for URL pattern detection
        PCT_RE: Compiled regex for percentage pattern detection
        DATE_HINTS: Set of tokens that suggest date/time columns
        NUM_HINTS: Set of tokens that suggest numeric columns
    """

    # Compiled regex patterns for efficiency
    EMAIL_RE = Constants.EMAIL_PATTERN
    PHONE_RE = Constants.PHONE_PATTERN
    URL_RE = Constants.URL_PATTERN
    PCT_RE = Constants.PERCENT_PATTERN

    # Type hint sets
    DATE_HINTS = Constants.DATE_TYPE_HINTS
    NUM_HINTS = Constants.NUMERIC_TYPE_HINTS

    def __init__(self) -> None:
        """Initialize the profiler with lightweight NER capabilities."""
        self.ner = _ner_instance

    def _is_numeric_type(self, sqlalchemy_type: str) -> bool:
        """Check if SQLAlchemy type string indicates a numeric type.

        Args:
            sqlalchemy_type: SQLAlchemy type string (e.g., 'INTEGER', 'DECIMAL')

        Returns:
            True if the type appears to be numeric
        """
        type_lower = sqlalchemy_type.lower()
        return any(hint in type_lower for hint in self.NUM_HINTS)

    def _is_text_type(self, sqlalchemy_type: str) -> bool:
        """Check if SQLAlchemy type string indicates a text type.

        Args:
            sqlalchemy_type: SQLAlchemy type string (e.g., 'VARCHAR', 'TEXT')

        Returns:
            True if the type appears to be text/string based
        """
        type_lower = sqlalchemy_type.lower()
        return ("char" in type_lower) or ("text" in type_lower) or ("clob" in type_lower)

    def infer_col_role(
        self,
        name: str,
        sqlalchemy_type: str,
        sample: pd.Series,
        *,
        is_pk: bool,
        is_fk: bool,
    ) -> tuple[str, list[str], list[str]]:
        """Infer semantic role and detect patterns in a column.

        Analyzes column name, type, and sample data to determine the semantic
        role of the column and detect common data patterns.

        Args:
            name: Column name
            sqlalchemy_type: SQLAlchemy type string
            sample: Pandas Series containing sampled column data
            is_pk: True if column is part of primary key
            is_fk: True if column is a foreign key

        Returns:
            Tuple of (role, semantic_tags, patterns) where:
            - role: Semantic role (key, date, metric, category, text, id)
            - semantic_tags: List of detected semantic tags
            - patterns: List of detected data patterns
        """
        semantic_tags: list[str] = []
        patterns: list[str] = []

        # Analyze sample of data (up to 50 values) with robust string conversion
        sample_size = min(50, len(sample))
        raw_values = sample.head(sample_size).dropna()

        def _to_display_str(value: Any) -> str:
            """Safely convert a value to a short display string.

            - Bytes: decode as UTF-8 with replacement; if still non-printable,
              show hex prefix limited in length.
            - Other: fall back to str(value).
            """
            try:
                if isinstance(value, (bytes | bytearray)):
                    try:
                        s = value.decode("utf-8", errors="replace")
                    except Exception:  # noqa: BLE001
                        # Fallback to hex representation
                        s = "0x" + bytes(value[:24]).hex()
                else:
                    s = str(value)
            except Exception:  # noqa: BLE001
                s = "<unprintable>"

            # Truncate long strings for prompt friendliness
            return s[:120]

        values = [_to_display_str(v) for v in raw_values.tolist()]  # type: ignore[misc]
        normalized_name = normalize_identifier(name)
        raw_lower = (name or "").lower()
        collapsed = re.sub(r"[^a-z0-9]", "", raw_lower)

        # Determine semantic role based on name and type
        if (
            # Prefer true temporal SQL types first
            any(x in sqlalchemy_type.lower() for x in ("date", "time", "datetime", "timestamp"))
            or (
                # Name-based hint only if the column type is not numeric
                any(hint in normalized_name for hint in self.DATE_HINTS)
                and not self._is_numeric_type(sqlalchemy_type)
            )
        ):
            role = "date"
        elif is_pk or is_fk or raw_lower.endswith("_id") or collapsed.endswith("id"):
            role = "key"
        elif self._is_numeric_type(sqlalchemy_type):
            # Distinguish between metrics and categories based on cardinality
            unique_count = sample.nunique(dropna=True) if len(sample) else 0
            role = "metric" if unique_count > MIN_UNIQUE_COUNT_FOR_METRIC else "category"
        elif self._is_text_type(sqlalchemy_type):
            role = "text"
        else:
            role = "category"

        # Pattern detection on sample values
        for value in values[:30]:  # Analyze first 30 values
            value_str = str(value)  # Ensure string type

            if self.EMAIL_RE.match(value_str):
                semantic_tags.append("email")
                patterns.append("email-like")
            elif self.PHONE_RE.match(value_str):
                semantic_tags.append("phone")
                patterns.append("phone-like")
            elif self.URL_RE.match(value_str):
                semantic_tags.append("url")
                patterns.append("url-like")
            elif self.PCT_RE.search(value_str):
                semantic_tags.append("unit:%")
                patterns.append("percent-like")

        # Named entity recognition using new LightweightNER
        try:
            ents = self.ner.analyze(name)
            ner_labels = [e.label.lower() for e in ents]
            semantic_tags.extend(ner_labels)
        except Exception as e:  # noqa: BLE001
            _logger.debug("Lightweight NER failed for column %s: %s", name, e)

        # Remove duplicates while preserving order
        semantic_tags = list(dict.fromkeys(semantic_tags))
        patterns = list(dict.fromkeys(patterns))

        return role, semantic_tags, patterns

    def profile_table(
        self,
        table_profile: TableProfile,
        data: pd.DataFrame,
        *,
        value_constraint_threshold: int = 20,
    ) -> TableProfile:
        """Analyze table data and update the table profile with insights.

        Processes the sampled table data to compute column statistics,
        infer semantic roles, and detect patterns for each column.

        Args:
            table_profile: TableProfile object to update with analysis results
            data: DataFrame containing sampled table data
            value_constraint_threshold: Maximum distinct values to store for constraint analysis

        Returns:
            Updated TableProfile with computed column metadata
        """
        table_profile.n_rows_sampled = len(data)

        for column in table_profile.columns:
            # Get column data or create empty series if column not found
            if column.name in data.columns:
                series: pd.Series = data[column.name]  # type: ignore[misc]
            else:
                series = pd.Series(dtype="object")

            # Calculate null rate
            if len(series):  # type: ignore[misc]
                column.null_rate = float(series.isna().mean())  # type: ignore[misc]
            else:
                column.null_rate = None

            # Calculate approximate distinct ratio
            if len(series):  # type: ignore[misc]
                unique_count = series.nunique(dropna=True)  # type: ignore[misc]
                total_count = max(1, len(series))  # type: ignore[misc]
                column.approx_distinct_ratio = float(unique_count / total_count)  # type: ignore[misc]
            else:
                column.approx_distinct_ratio = None
                unique_count = 0

            # Infer semantic role and detect patterns
            role_tuple: tuple[str, list[str], list[str]] = self.infer_col_role(
                column.name,
                column.type,
                series,  # type: ignore[arg-type]
                is_pk=column.is_pk,
                is_fk=column.is_fk,
            )
            role, tags, patterns = role_tuple

            column.role = role
            column.semantic_tags = tags
            column.sample_patterns = patterns

            # Capture value constraints for low-cardinality columns
            if len(series) and unique_count <= value_constraint_threshold:  # type: ignore[misc]
                # Store distinct values for enum-like columns
                non_null_series = series.dropna()  # type: ignore[misc]
                if len(non_null_series):  # type: ignore[misc]
                    column.distinct_values = sorted(non_null_series.unique())

                    # Store value range for numeric columns with low cardinality
                    if role == "metric" and self._is_numeric_type(column.type):
                        try:
                            numeric_series = pd.to_numeric(  # pyright: ignore[reportUnknownVariableType]
                                non_null_series, errors="coerce"
                            ).dropna()  # type: ignore[misc]
                            if len(numeric_series):  # type: ignore[misc]
                                min_val = numeric_series.min()  # type: ignore[misc]
                                max_val = numeric_series.max()  # type: ignore[misc]
                                column.value_range = (
                                    float(min_val),  # type: ignore[misc]
                                    float(max_val),  # type: ignore[misc]
                                )
                        except (ValueError, TypeError):
                            pass  # Skip if conversion fails

        return table_profile
