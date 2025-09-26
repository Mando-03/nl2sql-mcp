"""Data models for schema exploration.

This module contains all data classes and models used to represent database
schema information throughout the system. These models provide a structured
way to store and access metadata about tables, columns, and schema relationships.

Models:
- ColumnProfile: Detailed metadata about individual database columns
- TableProfile: Comprehensive information about database tables
- SchemaCard: Complete schema representation with relationships and metadata
- SchemaExplorerConfig: Configuration object for SchemaExplorer initialization
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any

from nl2sql_mcp.models import SubjectAreaData

from .constants import Constants


@dataclass
class ColumnProfile:
    """Profile containing detailed metadata about a database column.

    This class captures both structural metadata (name, type, constraints)
    and semantic information derived from data sampling and analysis.

    Attributes:
        name: Column name as defined in the database
        type: SQL data type string (normalized to lowercase)
        nullable: Whether the column accepts NULL values
        is_pk: True if this column is part of the primary key
        is_fk: True if this column is a foreign key reference
        fk_ref: Foreign key reference as (schema.table, pk_column) tuple
        null_rate: Proportion of NULL values in the sampled data (0.0-1.0)
        approx_distinct_ratio: Ratio of distinct values to total rows in sample
        sample_patterns: List of detected patterns in the column data
        semantic_tags: Semantic labels like "email", "phone", "url", "currency"
        role: Semantic role classification (key, date, metric, category, text, id)
        comment: Database comment/documentation if available
        distinct_values: List of actual distinct values for low-cardinality columns
        value_range: Min/max value tuple for bounded numeric columns
    """

    name: str
    type: str
    nullable: bool
    is_pk: bool = False
    is_fk: bool = False
    fk_ref: tuple[str, str] | None = None  # (schema.table, pk_col)
    null_rate: float | None = None
    approx_distinct_ratio: float | None = None
    sample_patterns: list[str] = field(default_factory=list)
    semantic_tags: list[str] = field(default_factory=list)
    role: str | None = None
    comment: str | None = None
    distinct_values: list[Any] | None = None
    value_range: tuple[Any, Any] | None = None


@dataclass
class TableProfile:
    """Comprehensive profile of a database table with metadata and analysis.

    This class contains both structural information about the table
    (columns, keys, constraints) and derived analytical metadata
    (archetype classification, subject area, summary).

    Attributes:
        schema: Database schema name containing this table
        name: Table name as defined in the database
        n_rows_sampled: Number of rows included in the data sample
        approx_rowcount: Estimated total number of rows in the table
        columns: List of ColumnProfile objects for all table columns
        fks: List of foreign key relationships as (col, ref_schema.table, ref_col)
        pk_cols: List of primary key column names
        comment: Database comment/documentation if available
        archetype: Table classification (fact, dimension, bridge, reference,
            operational)
        summary: Human-readable 1-2 sentence description of the table
        subject_area: Subject area/community identifier for schema organization
        centrality: Graph centrality measure indicating table importance
        n_metrics: Count of columns classified as metrics/measures
        n_dates: Count of columns classified as date/time columns
        is_archive: True if table appears to contain historical/archived data
        is_audit_like: True if table appears to be a generic system/audit table
    """

    schema: str
    name: str
    n_rows_sampled: int = 0
    approx_rowcount: int | None = None
    columns: list[ColumnProfile] = field(default_factory=list)
    fks: list[tuple[str, str, str]] = field(default_factory=list)
    pk_cols: list[str] = field(default_factory=list)
    comment: str | None = None
    archetype: str | None = None
    summary: str | None = None
    subject_area: str | None = None
    centrality: float | None = None
    # Derived analytical flags
    n_metrics: int = 0
    n_dates: int = 0
    is_archive: bool = False
    is_audit_like: bool = False


@dataclass
class SchemaCard:
    """Complete representation of a database schema with relationships.

    This is the main data structure that contains the complete analyzed
    schema information, including tables, relationships, and subject areas.
    It serves as the central knowledge base for query generation and
    schema understanding.

    Attributes:
        db_dialect: Database dialect/engine type (postgresql, mysql, etc.)
        db_url_fingerprint: Hash fingerprint of the database connection URL
        schemas: List of schema names included in the analysis
        subject_areas: Dictionary mapping area IDs to SubjectAreaData objects
        tables: Dictionary mapping "schema.table" keys to TableProfile objects
        edges: List of relationship edges as (src_table, dst_table, fk_description)
        built_at: Unix timestamp when this schema card was created
        reflection_hash: Hash of the reflection payload for change detection
    """

    db_dialect: str
    db_url_fingerprint: str
    schemas: list[str]
    subject_areas: dict[str, SubjectAreaData]
    tables: dict[str, TableProfile]  # key: "schema.table"
    edges: list[tuple[str, str, str]]  # (src_table, dst_table, fk_desc)
    built_at: float
    reflection_hash: str

    def to_json(self) -> str:
        """Serialize the schema card to JSON format.

        Returns:
            JSON string representation of the complete schema card
        """
        tables_dict = {}
        for key, table_profile in self.tables.items():
            table_dict = asdict(table_profile)
            table_dict["columns"] = [asdict(col) for col in table_profile.columns]
            tables_dict[key] = table_dict

        # Convert SubjectAreaData objects to dictionaries for serialization
        subject_areas_dict = {key: area.model_dump() for key, area in self.subject_areas.items()}

        return json.dumps(
            {
                "db_dialect": self.db_dialect,
                "db_url_fingerprint": self.db_url_fingerprint,
                "schemas": self.schemas,
                "subject_areas": subject_areas_dict,
                "tables": tables_dict,
                "edges": self.edges,
                "built_at": self.built_at,
                "reflection_hash": self.reflection_hash,
            },
            indent=2,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchemaCard:
        """Deserialize schema card from dictionary format.

        Args:
            data: Dictionary containing schema card data

        Returns:
            SchemaCard instance reconstructed from the dictionary
        """
        # Convert table dictionaries back to TableProfile objects
        tables = {}
        for key, table_dict in data["tables"].items():
            # Convert column dictionaries back to ColumnProfile objects
            columns = [ColumnProfile(**col_dict) for col_dict in table_dict["columns"]]

            # Create TableProfile with converted columns
            table_dict_copy = table_dict.copy()
            table_dict_copy["columns"] = columns
            tables[key] = TableProfile(**table_dict_copy)

        # Convert subject area dictionaries back to SubjectAreaData objects
        subject_areas = {
            key: SubjectAreaData(**area_dict) for key, area_dict in data["subject_areas"].items()
        }

        # Create SchemaCard with converted tables and subject areas
        data = data.copy()
        data["tables"] = tables
        data["subject_areas"] = subject_areas
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> SchemaCard:
        """Deserialize schema card from JSON string.

        Args:
            json_str: JSON string representation of schema card

        Returns:
            SchemaCard instance reconstructed from the JSON
        """
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class SchemaExplorerConfig:
    """Configuration object for SchemaExplorer initialization.

    This dataclass encapsulates all configuration parameters for the
    SchemaExplorer class, providing a clean interface and centralizing
    default values.

    Attributes:
        include_schemas: Optional list of schemas to include (whitelist)
        exclude_schemas: Optional list of schemas to exclude (blacklist)
        per_table_rows: Number of rows to sample per table
        sample_timeout: Timeout for sampling operations in seconds
        model_name: Name/path of the sentence transformer model
        build_column_index: Whether to build column-level embeddings
        max_cols_for_embeddings: Maximum columns per table for embeddings
        expander: Graph expansion algorithm type ("fk_following" or "simple")
        min_area_size: Minimum size for subject area communities
        merge_archive_areas: Whether to merge archive-dominated areas
        value_constraint_threshold: Max distinct values to store for constraint analysis
        fast_startup: Enable faster, shallow first build of the index
        max_tables_at_startup: Optional cap on number of tables reflected at startup
        max_sampled_columns: Maximum number of columns to sample per table
    """

    include_schemas: list[str] | None = None
    exclude_schemas: list[str] | None = None
    per_table_rows: int = Constants.DEFAULT_SAMPLE_ROWS
    sample_timeout: int = Constants.DEFAULT_TIMEOUT_SEC
    model_name: str = Constants.DEFAULT_EMBEDDING_MODEL
    build_column_index: bool = True
    max_cols_for_embeddings: int = Constants.DEFAULT_MAX_COLS_FOR_EMBEDDINGS
    expander: str = "fk_following"
    min_area_size: int = Constants.DEFAULT_MIN_AREA_SIZE
    merge_archive_areas: bool = True
    value_constraint_threshold: int = Constants.DEFAULT_VALUE_CONSTRAINT_THRESHOLD
    # Startup performance tunables
    fast_startup: bool = False
    max_tables_at_startup: int | None = None
    max_sampled_columns: int = 20
    # Reflection timeout (seconds) applied session-locally during metadata reflection
    reflect_timeout_sec: int = Constants.DEFAULT_TIMEOUT_SEC
    # Retrieval/expansion tuning
    strict_archive_exclude: bool = True
    lexicon_top_n: int = 16
    lexicon_min_df: int = 2
    morph_min_len: int = 3
