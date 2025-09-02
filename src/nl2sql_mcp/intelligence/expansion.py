"""Graph expansion algorithms for table relationship discovery.

This module provides algorithms for expanding a set of seed tables to include
related tables based on foreign key relationships. It includes both simple
neighbor expansion and FK-following approaches that find directly connected
tables while prioritizing by utility scores.

Classes:
- GraphExpander: Main class for graph expansion algorithms
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.utilities.logging import get_logger

from .constants import TableArchetype

if TYPE_CHECKING:
    from .models import SchemaCard

# Logger
_logger = get_logger("schema_explorer.expansion")


class GraphExpander:
    """Graph expander for table relationship discovery.

    This class provides algorithms to expand a set of seed tables by including
    related tables based on foreign key relationships. It uses graph algorithms
    to find optimal connections while considering table importance and relevance.

    Attributes:
        schema_card: Complete schema information with relationships
        expander_type: Type of expansion algorithm ("fk_following" or "simple")
    """

    def __init__(self, schema_card: SchemaCard, expander_type: str = "fk_following") -> None:
        """Initialize the graph expander.

        Args:
            schema_card: Complete schema card with table metadata and relationships
            expander_type: Type of expansion algorithm to use ("fk_following" or "simple")
        """
        self.schema_card = schema_card
        self.expander_type = expander_type

    def _compute_node_utility(self, table_key: str) -> float:
        """Compute utility score for a table node.

        Calculates how valuable a table is for inclusion in the result set
        based on its archetype, metrics, dates, and other characteristics.

        Args:
            table_key: Table identifier

        Returns:
            Utility score (higher is better)
        """
        table_profile = self.schema_card.tables[table_key]
        score = 0.0

        # Base score by archetype
        if table_profile.archetype == TableArchetype.FACT.value:
            score += 2.0
        elif table_profile.archetype == TableArchetype.DIMENSION.value:
            score += 1.0
        else:
            score += 0.5

        # Bonus for metrics and dates
        score += 0.3 * min(2, table_profile.n_metrics)
        score += 0.2 if table_profile.n_dates > 0 else 0.0

        # Centrality bonus (well-connected tables are often important)
        score += 0.2 * (table_profile.centrality or 0.0)

        # Penalties for less useful tables
        if table_profile.is_audit_like:
            score -= 0.5
        if table_profile.is_archive:
            score -= 0.6

        return score

    def expand_simple(self, seed_tables: list[str], k: int) -> list[str]:
        """Expand seed tables using simple neighbor inclusion.

        Includes all direct neighbors of the seed tables up to the limit.
        This is a fast but less sophisticated approach.

        Args:
            seed_tables: List of seed table keys
            k: Maximum number of tables to return

        Returns:
            List of table keys including seeds and neighbors
        """
        if not seed_tables:
            return []

        seed_set = set(seed_tables)
        neighbors: set[str] = set()
        valid_tables = set(self.schema_card.tables.keys())

        # Find all direct neighbors of seed tables
        for source_table, target_table, _ in self.schema_card.edges:
            if source_table in seed_set and target_table in valid_tables:
                neighbors.add(target_table)
            if target_table in seed_set and source_table in valid_tables:
                neighbors.add(source_table)

        # Combine seeds and neighbors, limit to k tables
        result_set = seed_set.union(neighbors)
        return [table for table in list(result_set)[:k] if table in valid_tables]

    def expand_fk_following(self, seed_tables: list[str], k: int) -> list[str]:  # noqa: PLR0912
        """Expand seed tables using FK-following algorithm.

        Follows foreign key relationships from seed tables to find directly
        connected neighbors, prioritizing by table utility.

        Args:
            seed_tables: List of seed table keys
            k: Maximum number of tables to return

        Returns:
            List of table keys including seeds and FK-connected neighbors
        """
        # Filter to valid seed tables
        valid_seeds = [table for table in seed_tables if table in self.schema_card.tables]
        if not valid_seeds or k <= 0:
            return []

        selected_tables: list[str] = []
        selected_set: set[str] = set()

        # Add seed tables first
        for seed in valid_seeds:
            if len(selected_tables) < k:
                selected_tables.append(seed)
                selected_set.add(seed)

        # Find all direct FK neighbors of selected tables
        neighbor_scores: list[tuple[float, str]] = []

        # Determine primary subject area from first seed (if available)
        main_area = None
        if valid_seeds:
            main_tp = self.schema_card.tables.get(valid_seeds[0])
            main_area = main_tp.subject_area if main_tp else None

        for source_table, target_table, _ in self.schema_card.edges:
            # Check if we have a connection from selected to unselected table
            if (
                source_table in selected_set
                and target_table not in selected_set
                and target_table in self.schema_card.tables
            ):
                utility = self._compute_node_utility(target_table)
                # Subject-area consistency bonus
                if main_area is not None:
                    tp = self.schema_card.tables.get(target_table)
                    if tp and tp.subject_area == main_area:
                        utility += 0.2
                neighbor_scores.append((utility, target_table))
            elif (
                target_table in selected_set
                and source_table not in selected_set
                and source_table in self.schema_card.tables
            ):
                utility = self._compute_node_utility(source_table)
                if main_area is not None:
                    tp = self.schema_card.tables.get(source_table)
                    if tp and tp.subject_area == main_area:
                        utility += 0.2
                neighbor_scores.append((utility, source_table))

        # Sort neighbors by utility (descending) and add until we reach k
        neighbor_scores.sort(key=lambda x: -x[0])
        for _, neighbor in neighbor_scores:
            if len(selected_tables) >= k:
                break
            if neighbor not in selected_set:
                selected_tables.append(neighbor)
                selected_set.add(neighbor)

        return selected_tables[:k]

    def expand(self, seed_tables: list[str], k: int) -> list[str]:
        """Expand seed tables using the configured algorithm.

        Args:
            seed_tables: List of seed table keys
            k: Maximum number of tables to return

        Returns:
            List of expanded table keys
        """
        if self.expander_type == "fk_following":
            return self.expand_fk_following(seed_tables, k)
        return self.expand_simple(seed_tables, k)
