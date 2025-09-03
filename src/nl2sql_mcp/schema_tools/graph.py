"""Graph building and table classification.

This module provides classes for building relationship graphs from database
schema metadata and classifying tables based on their structure and
relationships. It includes community detection and table archetype
classification using dimensional modeling principles.

Classes:
- GraphBuilder: Creates NetworkX graphs from table relationships
- Classifier: Classifies tables into archetypes and generates summaries
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.utilities.logging import get_logger
import networkx as nx

from .constants import TableArchetype

if TYPE_CHECKING:
    from .models import TableProfile

# Classification thresholds
MIN_PK_COLS_FOR_BRIDGE = 2
MAX_NON_KEY_COLS_FOR_BRIDGE = 1
MIN_CONNECTIONS_FOR_BRIDGE = 2
MIN_METRICS_FOR_FACT = 2
MIN_DATES_FOR_FACT = 1
MIN_CONNECTIONS_FOR_FACT = 2
MIN_IN_DEGREE_FOR_DIMENSION = 2
MAX_METRICS_FOR_DIMENSION = 1
MAX_COLS_FOR_REFERENCE = 4
MIN_CONNECTIONS_FOR_REFERENCE = 1

# Logger
_logger = get_logger("schema_explorer.graph")


class GraphBuilder:
    """Builder for relationship graphs from database schema metadata.

    This class constructs NetworkX directed graphs representing foreign key
    relationships between database tables. It also computes graph metrics
    like centrality and performs community detection to identify subject areas.
    """

    def build(self, tables: dict[str, TableProfile]) -> nx.DiGraph[str]:
        """Build a directed graph from table relationships.

        Creates a NetworkX directed graph where nodes represent tables
        and edges represent foreign key relationships.

        Args:
            tables: Dictionary mapping table keys to TableProfile objects

        Returns:
            NetworkX directed graph with table relationships
        """
        graph: nx.DiGraph[str] = nx.DiGraph()

        # Add all tables as nodes
        for table_key in tables:
            graph.add_node(table_key)

        # Add foreign key relationships as edges
        for table_key, table_profile in tables.items():
            for column_name, ref_table, ref_column in table_profile.fks:
                if ref_table in tables:
                    # Create edge with foreign key description
                    fk_description = f"{table_key}.{column_name}->{ref_table}.{ref_column}"
                    graph.add_edge(table_key, ref_table, fk=fk_description)

        return graph

    def compute_metrics_and_communities(
        self, graph: nx.DiGraph[str]
    ) -> tuple[dict[str, float], dict[str, int]]:
        """Compute graph centrality metrics and detect communities.

        Calculates degree centrality for all nodes and uses greedy modularity
        maximization to detect communities (subject areas).

        Args:
            graph: NetworkX directed graph of table relationships

        Returns:
            Tuple of (centrality_dict, community_dict) where:
            - centrality_dict: Maps table keys to degree centrality scores
            - community_dict: Maps table keys to community IDs
        """
        # Convert to undirected graph for centrality and community detection
        undirected_graph = graph.to_undirected()

        # Compute degree centrality
        centrality = nx.degree_centrality(undirected_graph)

        # Detect communities using greedy modularity maximization
        if undirected_graph.number_of_edges() > 0:
            communities_list = nx.algorithms.community.greedy_modularity_communities(
                undirected_graph
            )
        else:
            # If no edges, put all nodes in one community
            communities_list = [set(undirected_graph.nodes())]

        # Build community mapping
        communities: dict[str, int] = {}
        for community_id, community_nodes in enumerate(communities_list):
            for node in community_nodes:
                communities[node] = community_id

        return centrality, communities


class Classifier:
    """Table classifier for archetype detection and summarization.

    This class analyzes table structure, relationships, and column roles
    to classify tables into dimensional modeling archetypes and generate
    human-readable summaries.
    """

    def classify_table(self, table_profile: TableProfile, graph: nx.DiGraph[str]) -> str:
        """Classify a table into a dimensional modeling archetype.

        Uses heuristics based on table structure, column roles, and graph
        position to classify tables into fact, dimension, bridge, reference,
        or operational archetypes.

        Args:
            table_profile: TableProfile object to classify
            graph: NetworkX graph containing relationship information

        Returns:
            Table archetype string (fact, dimension, bridge, reference, operational)
        """
        # Count column roles
        num_metrics = sum(1 for col in table_profile.columns if col.role == "metric")
        num_dates = sum(1 for col in table_profile.columns if col.role == "date")

        # Count non-key columns
        non_fk_non_key_columns = [
            col for col in table_profile.columns if not col.is_fk and not col.is_pk
        ]

        # Get graph degree information
        table_node = f"{table_profile.schema}.{table_profile.name}"
        if table_node in graph:
            out_degree = graph.out_degree[table_node]  # type: ignore[misc]
            in_degree = graph.in_degree[table_node]  # type: ignore[misc]
        else:
            out_degree = 0
            in_degree = 0
        total_degree = int(out_degree) + int(in_degree)

        # Bridge table detection
        # - Compound primary key with all FK columns
        # - Few or no non-key columns
        # - Connected to multiple tables
        if (
            len(table_profile.pk_cols) >= MIN_PK_COLS_FOR_BRIDGE
            and all(col.is_fk for col in table_profile.columns if col.is_pk)
            and len(non_fk_non_key_columns) <= MAX_NON_KEY_COLS_FOR_BRIDGE
            and total_degree >= MIN_CONNECTIONS_FOR_BRIDGE
        ):
            return TableArchetype.BRIDGE.value

        # Fact table detection
        # - Multiple metrics and at least one date
        # - Well connected in the graph
        if (
            num_metrics >= MIN_METRICS_FOR_FACT
            and num_dates >= MIN_DATES_FOR_FACT
            and total_degree >= MIN_CONNECTIONS_FOR_FACT
        ):
            return TableArchetype.FACT.value

        # Dimension table detection
        # - Referenced by multiple tables (high in-degree)
        # - Few or no metrics
        # - Single primary key
        if (
            in_degree >= MIN_IN_DEGREE_FOR_DIMENSION
            and num_metrics <= MAX_METRICS_FOR_DIMENSION
            and len(table_profile.pk_cols) == 1
        ):
            return TableArchetype.DIMENSION.value

        # Reference table detection
        # - Small, simple tables with few columns
        # - No metrics, mostly categorical data
        # - Connected to other tables
        if (
            len(table_profile.columns) <= MAX_COLS_FOR_REFERENCE
            and num_metrics == 0
            and total_degree >= MIN_CONNECTIONS_FOR_REFERENCE
        ):
            return TableArchetype.REFERENCE.value

        # Default to operational
        return TableArchetype.OPERATIONAL.value

    def summarize_table(self, table_profile: TableProfile) -> str:
        """Generate a human-readable summary of a table.

        Creates a concise summary including table archetype, key columns,
        important measures and dimensions, and foreign key relationships.

        Args:
            table_profile: TableProfile object to summarize

        Returns:
            Human-readable table summary string
        """
        # Extract key information from columns
        key_columns = [col.name for col in table_profile.columns if col.role == "key"][:3]
        date_columns = [col.name for col in table_profile.columns if col.role == "date"][:2]
        metric_columns = [col.name for col in table_profile.columns if col.role == "metric"][:5]
        dimension_columns = [
            col.name for col in table_profile.columns if col.role in ("category", "text")
        ][:6]

        # Build summary parts
        table_name = f"{table_profile.schema}.{table_profile.name}"
        archetype = table_profile.archetype or "table"
        summary_parts = [f"{table_name} is a {archetype}"]

        if key_columns:
            summary_parts.append(f"keys: {', '.join(key_columns)}")

        if date_columns:
            summary_parts.append(f"dates: {', '.join(date_columns)}")

        if metric_columns:
            summary_parts.append(f"measures: {', '.join(metric_columns)}")

        if dimension_columns:
            summary_parts.append(f"top dims: {', '.join(dimension_columns)}")

        # Add foreign key relationships
        if table_profile.fks:
            fk_descriptions = [
                f"{col}->{ref_table.split('.')[-1]}" for col, ref_table, _ in table_profile.fks
            ][:4]
            summary_parts.append(f"joins: {', '.join(fk_descriptions)}")

        return "; ".join(summary_parts)
