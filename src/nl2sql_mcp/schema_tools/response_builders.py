"""Response builders for nl2sql-mcp.

This module contains builder classes that construct response models from
schema analysis results. Each builder is responsible for transforming
intelligence analysis data into structured models suitable for MCP responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

import sqlalchemy as sa

from nl2sql_mcp.models import (
    ColumnDetail,
    DatabaseSummary,
    FilterCandidate,
    ForeignKeyRef,
    JoinExample,
    JoinPlanStep,
    QuerySchemaResult,
    SelectedColumn,
    TableInfo,
    TableSummary,
)
from nl2sql_mcp.schema_tools.explorer import SchemaExplorer
from nl2sql_mcp.schema_tools.utils import tokens_from_text

if TYPE_CHECKING:
    from nl2sql_mcp.schema_tools.models import TableProfile

# Constants for magic values
MAX_DISTINCT_VALUES_FOR_FILTERS = 10
FK_DESCRIPTION_PARTS_COUNT = 2
FK_TABLE_PARTS_MIN_COUNT = 2


class QuerySchemaResultBuilder:
    """Builder for QuerySchemaResult objects."""

    @staticmethod
    def build(  # noqa: PLR0913 - explicit detail controls improve LLM ergonomics
        query: str,
        selected_tables: list[str],
        explorer: SchemaExplorer,
        *,
        detail_level: Literal["minimal", "standard", "full"] = "standard",
        include_samples: bool = False,
        max_sample_values: int = 3,
        max_columns_per_table: int = 20,
        join_limit: int = 8,
    ) -> QuerySchemaResult:
        """Build query schema result with actionable SQL information.

        Args:
            query: Natural language query being analyzed
            selected_tables: List of table keys relevant to the query
            explorer: SchemaExplorer instance with built schema card

        Returns:
            QuerySchemaResult with simplified schema information optimized for SQL generation

        Raises:
            RuntimeError: If schema card is not available
        """
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        # Normalize detail controls
        samples = include_samples and detail_level != "minimal"
        columns_cap = 6 if detail_level == "minimal" else max_columns_per_table
        joins_cap = 3 if detail_level == "minimal" else join_limit

        # Build suggested approach first to determine main table and dims
        suggested_approach, main_table, dims_sorted = (
            QuerySchemaResultBuilder._build_suggested_approach(query, selected_tables, explorer)
        )

        # Ensure connectivity: add one-hop bridges between main_table and other selections
        if main_table:
            selected_tables = QuerySchemaResultBuilder._augment_with_bridges(
                selected_tables, explorer, main_table
            )

        # Build table summaries and key columns using possibly augmented set
        relevant_tables, key_columns = QuerySchemaResultBuilder._build_table_summaries(
            selected_tables,
            explorer,
            include_samples=samples,
            max_sample_values=max_sample_values,
            max_columns_per_table=columns_cap,
        )

        # Build JOIN examples with anchoring to main table and query tokens
        join_examples = QuerySchemaResultBuilder._build_join_examples(
            selected_tables,
            explorer,
            limit=joins_cap,
            main_table=main_table,
            query=query,
        )

        join_plan = QuerySchemaResultBuilder._build_join_plan(
            join_examples, explorer, limit=joins_cap
        )
        group_by_candidates = QuerySchemaResultBuilder._build_group_by_candidates(
            main_table, dims_sorted, explorer, max_items=8
        )
        filter_candidates = QuerySchemaResultBuilder._build_filter_candidates(
            selected_tables, explorer, max_items=10
        )
        selected_columns = QuerySchemaResultBuilder._build_selected_columns(
            main_table, dims_sorted, explorer, max_items=8
        )

        return QuerySchemaResult(
            query=query,
            relevant_tables=relevant_tables,
            join_examples=join_examples,
            suggested_approach=suggested_approach,
            key_columns=key_columns,
            main_table=main_table,
            join_plan=join_plan,
            group_by_candidates=group_by_candidates,
            filter_candidates=filter_candidates,
            selected_columns=selected_columns,
        )

    @staticmethod
    def _augment_with_bridges(
        selected_tables: list[str], explorer: SchemaExplorer, main_table: str
    ) -> list[str]:
        """Add one-hop bridge tables to ensure joinability from main_table.

        For any selected table not directly connected to the main_table,
        if there exists an intermediate table X such that main_table—X and X—T
        are edges, include X in the selection. Keeps original order, de-duplicates.
        """
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)
        if main_table not in explorer.card.tables:
            return selected_tables

        # Build undirected adjacency and fk map for quick neighbor checks
        adj: dict[str, set[str]] = {}
        edge_fk: dict[frozenset[str], list[str]] = {}
        for a, b, fk in explorer.card.edges:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
            edge_fk.setdefault(frozenset({a, b}), []).append(fk)

        out: list[str] = []
        seen: set[str] = set()

        def add(t: str) -> None:
            if t not in seen:
                out.append(t)
                seen.add(t)

        # Always keep the original order
        for t in list(selected_tables):
            add(t)
            if t == main_table:
                continue
            # If already directly connected, nothing to do
            if t in adj.get(main_table, set()):
                continue
            # Try one-hop bridge with scoring
            bridge_candidates = adj.get(main_table, set())
            best_x: str | None = None
            best_score = float("-inf")
            found_bridge = False

            def _score_bridge(x: str, dest: str) -> float:
                score = 0.0
                card = explorer.card
                if card is None:
                    msg_local = "Schema card not available"
                    raise RuntimeError(msg_local)
                tp_x = card.tables.get(x)
                tp_main = card.tables.get(main_table)
                tp_t = card.tables.get(dest)
                # Avoid audit-like bridges
                if tp_x and tp_x.is_audit_like:
                    score -= 0.6
                # Subject area consistency
                if tp_x and tp_main and tp_x.subject_area == tp_main.subject_area:
                    score += 0.2
                if tp_x and tp_t and tp_x.subject_area == tp_t.subject_area:
                    score += 0.2

                # Inspect FK columns for admin patterns vs business keys (generic, DB-agnostic)
                admin_tokens = {
                    "last",
                    "edited",
                    "edit",
                    "lastedited",
                    "lasteditedby",
                    "created",
                    "create",
                    "createdby",
                    "modified",
                    "modify",
                    "modifiedby",
                    "update",
                    "updated",
                    "updatedby",
                    "change",
                    "changed",
                }
                identity_tokens = {
                    "user",
                    "users",
                    "person",
                    "people",
                    "employee",
                    "employees",
                    "staff",
                    "account",
                    "accounts",
                    "login",
                    "logon",
                    "owner",
                    "ownerid",
                }

                def _edge_penalty(u: str, v: str) -> float:
                    fks = edge_fk.get(frozenset({u, v}), [])
                    pen = 0.0
                    for fkdesc in fks:
                        if "->" not in fkdesc:
                            continue
                        left, right = fkdesc.split("->", 1)
                        lcol = left.split(".")[-1]
                        rcol = right.split(".")[-1]
                        ltok = set(tokens_from_text(lcol))
                        rtok = set(tokens_from_text(rcol))
                        if ltok & admin_tokens or rtok & admin_tokens:
                            pen -= 0.5
                        # Penalize common admin bridge patterns: admin column -> identity reference
                        if (ltok & admin_tokens and (rtok & identity_tokens)) or (
                            rtok & admin_tokens and (ltok & identity_tokens)
                        ):
                            pen -= 0.4
                        # Small preference for clean ID joins
                        has_left_id = "id" in ltok and not (ltok & admin_tokens)
                        has_right_id = "id" in rtok and not (rtok & admin_tokens)
                        if has_left_id or has_right_id:
                            pen += 0.1
                    # Penalize if bridge table name looks like a generic identity table
                    name_toks = set(tokens_from_text(x))
                    if name_toks & identity_tokens:
                        pen -= 0.2
                    return pen

                score += _edge_penalty(main_table, x)
                score += _edge_penalty(x, dest)
                return score

            for x in bridge_candidates:
                if t in adj.get(x, set()) and x in explorer.card.tables:
                    s = _score_bridge(x, t)
                    if s > best_score:
                        best_score = s
                        best_x = x

            if best_x is not None:
                add(best_x)
                # found_bridge kept for clarity; no further use here
                found_bridge = True
            if not found_bridge:
                # leave as-is; could be two+ hops (not handled here)
                pass

        return out

    @staticmethod
    def _build_table_summaries(
        selected_tables: list[str],
        explorer: SchemaExplorer,
        *,
        include_samples: bool,
        max_sample_values: int,
        max_columns_per_table: int,
    ) -> tuple[list[TableSummary], dict[str, list[str]]]:
        """Build table summaries and key columns mapping."""
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        relevant_tables: list[TableSummary] = []
        key_columns: dict[str, list[str]] = {}

        for table_key in selected_tables:
            table_profile = explorer.card.tables.get(table_key)
            if not table_profile:
                continue

            columns = QuerySchemaResultBuilder._build_column_details(
                table_profile,
                include_samples=include_samples,
                max_sample_values=max_sample_values,
                max_columns=max_columns_per_table,
            )
            common_filters = QuerySchemaResultBuilder._build_common_filters(table_profile)
            table_key_columns = QuerySchemaResultBuilder._extract_key_columns(table_profile)

            table_summary = TableSummary(
                name=table_key,
                business_purpose=table_profile.summary
                or f"{table_profile.archetype or 'data'} table",
                columns=columns,
                primary_keys=table_profile.pk_cols,
                common_filters=common_filters,
            )
            relevant_tables.append(table_summary)
            key_columns[table_key] = table_key_columns

        return relevant_tables, key_columns

    @staticmethod
    def _build_column_details(
        table_profile: TableProfile,
        *,
        include_samples: bool,
        max_sample_values: int,
        max_columns: int,
    ) -> list[ColumnDetail]:
        """Build column details for a table."""
        columns: list[ColumnDetail] = []

        for col in table_profile.columns[:max_columns]:
            # Get sample values
            sample_values = []
            if include_samples and col.distinct_values:
                sample_values = [str(v) for v in col.distinct_values[:max_sample_values]]

            # Build constraints list
            constraints: list[str] = []
            if col.distinct_values:
                constraints.append(
                    f"Enum: {', '.join(str(v) for v in col.distinct_values[:max_sample_values])}"
                )
            if col.value_range:
                constraints.append(f"Range: {col.value_range[0]}-{col.value_range[1]}")

            # Determine business role
            business_role = col.role or "data"
            if col.is_pk:
                business_role = "primary key"
            elif col.is_fk:
                business_role = "foreign key"

            column_detail = ColumnDetail(
                name=col.name,
                data_type=_sanitize_sql_type(col.type),  # Prominently display type
                nullable=col.nullable,
                is_primary_key=col.is_pk,
                is_foreign_key=col.is_fk,
                business_role=business_role,
                sample_values=sample_values,
                constraints=constraints,
            )
            columns.append(column_detail)

        return columns

    @staticmethod
    def _build_common_filters(table_profile: TableProfile) -> list[str]:
        """Build common filters for a table."""
        common_filters: list[str] = []
        for col in table_profile.columns:
            if col.distinct_values and len(col.distinct_values) <= MAX_DISTINCT_VALUES_FOR_FILTERS:
                values_str = ", ".join(f"'{v}'" for v in col.distinct_values[:3])
                common_filters.append(f"{col.name} IN ({values_str})")
            elif col.role == "date":
                common_filters.append(f"{col.name} >= 'YYYY-MM-DD'")
        return common_filters

    @staticmethod
    def _extract_key_columns(table_profile: TableProfile) -> list[str]:
        """Extract key columns from a table profile."""
        return [
            col.name
            for col in table_profile.columns
            if col.is_pk or col.is_fk or col.role in ["date", "metric"] or col.distinct_values
        ]

    @staticmethod
    def _build_join_examples(
        selected_tables: list[str],
        explorer: SchemaExplorer,
        *,
        limit: int,
        main_table: str | None = None,
        query: str | None = None,
    ) -> list[JoinExample]:
        """Build ranked JOIN examples, anchoring to main table and query tokens."""
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        qtokens = set(tokens_from_text(query or ""))

        scored: list[tuple[float, JoinExample]] = []
        for edge in explorer.card.edges:
            if edge[0] in selected_tables and edge[1] in selected_tables:
                je = QuerySchemaResultBuilder._create_join_example(edge, explorer)
                if not je:
                    continue
                score = 0.0
                # Anchor: edges touching the main table first
                if main_table and (main_table in (je.from_table, je.to_table)):
                    score += 1.0
                # Prefer fact→dimension
                a = explorer.card.tables.get(je.from_table)
                b = explorer.card.tables.get(je.to_table)
                if a and b and (a.archetype == "fact" and b.archetype == "dimension"):
                    score += 0.2
                # Query token overlap with either table key
                ftoks = set(tokens_from_text(je.from_table))
                ttoks = set(tokens_from_text(je.to_table))
                if qtokens & (ftoks | ttoks):
                    score += 0.2
                # Downrank dim↔dim and self-joins unless anchored
                if a and b and a.archetype == b.archetype == "dimension":
                    score -= 0.2
                if je.from_table == je.to_table and not (
                    main_table and je.from_table == main_table
                ):
                    score -= 0.3
                scored.append((score, je))

        scored.sort(key=lambda x: -x[0])
        return [je for _s, je in scored[:limit]]

    @staticmethod
    def _create_join_example(
        edge: tuple[str, str, str], explorer: SchemaExplorer
    ) -> JoinExample | None:
        """Create a JOIN example from an edge."""
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        # Parse FK description to get column names
        fk_desc = edge[2]  # Format: "table1.col1->table2.col2"
        if "->" not in fk_desc:
            return None

        parts = fk_desc.split("->")
        if len(parts) != FK_DESCRIPTION_PARTS_COUNT:
            return None

        from_parts = parts[0].split(".")
        to_parts = parts[1].split(".")
        if len(from_parts) < FK_TABLE_PARTS_MIN_COUNT or len(to_parts) < FK_TABLE_PARTS_MIN_COUNT:
            return None

        from_col = from_parts[-1]
        to_col = to_parts[-1]

        # Create SQL JOIN syntax via SQLAlchemy for dialect safety
        sql_syntax = _compile_join_clause(edge[0], edge[1], from_col, to_col, explorer)

        # Determine relationship type and purpose
        from_profile = explorer.card.tables.get(edge[0])
        to_profile = explorer.card.tables.get(edge[1])

        relationship_type = "1:many"  # Default assumption
        from_archetype = from_profile.archetype if from_profile else "records"
        to_archetype = to_profile.archetype if to_profile else "related data"
        business_purpose = f"{from_archetype} → {to_archetype}"

        return JoinExample(
            from_table=edge[0],
            to_table=edge[1],
            sql_syntax=sql_syntax,
            relationship_type=relationship_type,
            business_purpose=business_purpose,
        )

    @staticmethod
    def _build_suggested_approach(
        query: str, selected_tables: list[str], explorer: SchemaExplorer
    ) -> tuple[str, str | None, list[str]]:
        """Build a more actionable suggested approach text.

        Heuristic: pick a likely fact table (metrics+dates preferred), then
        suggest joining key dimensions (entities, categories, dates) and outline
        GROUP BY/ORDER BY steps. Avoids any schema-specific keywords.
        """
        main = selected_tables[:]
        if not main:
            return (
                (
                    f"Query: {query}\n1. Identify a fact-like table\n"
                    "2. Join to key dimensions (entities/dates)\n3. Aggregate and rank"
                ),
                None,
                [],
            )

        # Rank candidates by heuristic using explorer card
        def score_table(tk: str) -> float:
            if not explorer.card or tk not in explorer.card.tables:
                return 0.0
            tp = explorer.card.tables[tk]
            score = 0.0
            if (tp.n_metrics or 0) > 0:
                score += 2.0
            if (tp.n_dates or 0) > 0:
                score += 1.0
            if (tp.archetype or "").lower() == "fact":
                score += 1.5
            score += 0.3 * (tp.centrality or 0.0)
            # New: lexical overlap of query tokens with table key and columns
            qtokens = set(tokens_from_text(query))
            name_toks = set(tokens_from_text(tk))
            overlap = len(qtokens & name_toks)
            if overlap:
                score += 0.4 + 0.1 * min(2, overlap - 1)
            return score

        # Choose main fact-like table
        main_sorted = sorted(main, key=score_table, reverse=True)
        main_table = main_sorted[0]

        # Identify likely dimensions connected to the main table
        dim_candidates: list[str] = []
        if explorer.card:
            for edge in explorer.card.edges:
                a, b = edge[0], edge[1]
                if a == main_table and b in main:
                    dim_candidates.append(b)
                elif b == main_table and a in main:
                    dim_candidates.append(a)

        # Rank dimensions by archetype and column roles (DB-agnostic)
        def dim_score(tk: str) -> float:
            if not explorer.card or tk not in explorer.card.tables:
                return 0.0
            tp = explorer.card.tables[tk]
            score = 0.0
            if (tp.archetype or "").lower() == "dimension":
                score += 1.0
            # Prefer dimensions rich in categorical attributes
            cat_count = sum(1 for c in tp.columns if c.role == "category")
            score += 0.15 * min(8, cat_count)
            # Small bonus for having dates (slowly changing or dated dims)
            if tp.n_dates > 0:
                score += 0.3
            return score

        dims_sorted = sorted(set(dim_candidates), key=dim_score, reverse=True)[:3]

        dims_str = ", ".join(dims_sorted) if dims_sorted else "key dimensions"
        return (
            f"Query: {query}\n"
            f"1. Main table: {main_table}\n"
            f"2. Join: {main_table} → {dims_str}\n"
            "3. Aggregate metric(s), GROUP BY dimension(s)\n"
            "4. ORDER BY metric DESC and limit/top",
            main_table,
            dims_sorted,
        )

    @staticmethod
    def _build_join_plan(
        join_examples: list[JoinExample], _explorer: SchemaExplorer, *, limit: int
    ) -> list[JoinPlanStep]:
        """Build a structured join plan derived from join examples.

        Note: ON pairs are left empty until richer metadata is available.
        """
        return [
            JoinPlanStep(
                from_table=j.from_table,
                to_table=j.to_table,
                on=[],
                relationship_type=j.relationship_type,
                purpose=j.business_purpose,
            )
            for j in join_examples[:limit]
        ]

    @staticmethod
    def _build_group_by_candidates(
        main_table: str | None, dims_sorted: list[str], explorer: SchemaExplorer, *, max_items: int
    ) -> list[str]:
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)
        out: list[str] = []
        # Prefer dimension labels first, then dates from main table
        # 1) Dimension category columns
        for tk in dims_sorted:
            tp = explorer.card.tables.get(tk) if tk else None
            if not tp:
                continue
            for col in tp.columns:
                if col.role == "category":
                    out.append(f"{tk}.{col.name}")
                    if len(out) >= max_items:
                        return out
        # 2) Dates from main table
        for tk in [main_table]:
            if not tk:
                continue
            tp = explorer.card.tables.get(tk) if tk else None
            if not tp:
                continue
            for col in tp.columns:
                if col.role == "date":
                    out.append(f"{tk}.{col.name}")
                    if len(out) >= max_items:
                        return out
        return out

    @staticmethod
    def _build_filter_candidates(
        selected_tables: list[str], explorer: SchemaExplorer, *, max_items: int
    ) -> list[FilterCandidate]:
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)
        out: list[FilterCandidate] = []
        # Capture non-optional card for inner closure (type-narrowing friendly)
        card = explorer.card

        # Prioritize date filters first, then metrics, then low-cardinality enums
        def add_candidates(kind: str) -> None:
            nonlocal out
            for tk in selected_tables:
                tp = card.tables.get(tk)
                if not tp:
                    continue
                for col in tp.columns:
                    if len(out) >= max_items:
                        return
                    if kind == "date" and col.role == "date":
                        out.append(
                            FilterCandidate(
                                table=tk,
                                column=col.name,
                                operator_examples=[">=", "<=", "BETWEEN"],
                            )
                        )
                    elif kind == "metric" and col.role == "metric":
                        out.append(
                            FilterCandidate(
                                table=tk, column=col.name, operator_examples=[">=", "<=", ">", "<"]
                            )
                        )
                    elif (
                        kind == "enum"
                        and col.distinct_values
                        and (len(col.distinct_values) <= MAX_DISTINCT_VALUES_FOR_FILTERS)
                    ):
                        out.append(
                            FilterCandidate(
                                table=tk, column=col.name, operator_examples=["=", "IN"]
                            )
                        )

        add_candidates("date")
        if len(out) < max_items:
            add_candidates("metric")
        if len(out) < max_items:
            add_candidates("enum")
        return out

    @staticmethod
    def _build_selected_columns(
        main_table: str | None, dims_sorted: list[str], explorer: SchemaExplorer, *, max_items: int
    ) -> list[SelectedColumn]:
        if not explorer.card or not main_table:
            return []
        out: list[SelectedColumn] = []
        tp = explorer.card.tables.get(main_table)
        if tp:
            for col in tp.columns:
                if col.role == "metric":
                    out.append(SelectedColumn(table=main_table, column=col.name, reason="metric"))
                    break
            for col in tp.columns:
                if col.role == "date" or col.is_pk:
                    out.append(SelectedColumn(table=main_table, column=col.name, reason="date/id"))
                    break
        for dim in dims_sorted[:2]:
            d = explorer.card.tables.get(dim)
            if not d:
                continue
            for col in d.columns:
                if col.role == "category":
                    out.append(SelectedColumn(table=dim, column=col.name, reason="group label"))
                    break
        return out[:max_items]


class DatabaseSummaryBuilder:
    """Builder for DatabaseSummary objects."""

    IMPORTANT_TABLE_LIMIT = 8

    @staticmethod
    def build(  # noqa: PLR0912 - controlled branching for clarity
        explorer: SchemaExplorer,
        *,
        include_subject_areas: bool = False,
        area_limit: int = 8,
    ) -> DatabaseSummary:
        """Build database summary with business context.

        Args:
            explorer: SchemaExplorer instance with built schema card

        Returns:
            DatabaseSummary with high-level database information

        Raises:
            RuntimeError: If schema card is not available
        """
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        # Build key subject areas with business context
        key_subject_areas: dict[str, str] = {}
        card = explorer.card
        for area_id, area_data in card.subject_areas.items():
            # Use the meaningful area name as key, fallback to descriptive format if name is empty
            area_key = area_data.name or f"Subject Area {area_id}"
            key_subject_areas[area_key] = (
                area_data.summary or f"Area: {len(area_data.tables)} tables"
            )
        subject_areas = None
        if include_subject_areas:
            # Limit by number of tables in each area
            sorted_ids = sorted(
                card.subject_areas.keys(),
                key=lambda aid: len(card.subject_areas[aid].tables),
                reverse=True,
            )
            subject_areas = {
                aid: card.subject_areas[aid] for aid in sorted_ids[: max(1, area_limit)]
            }

        # Get most important tables: centrality, excluding audit-like/archive tables first
        important_tables: list[str] = []
        sorted_tables = sorted(
            explorer.card.tables.items(), key=lambda x: x[1].centrality or 0, reverse=True
        )
        for table_key, tp in sorted_tables:
            if tp.is_audit_like or tp.is_archive:
                continue
            important_tables.append(table_key)
            if len(important_tables) >= DatabaseSummaryBuilder.IMPORTANT_TABLE_LIMIT:
                break
        # Fallback if too few after filtering
        if len(important_tables) < DatabaseSummaryBuilder.IMPORTANT_TABLE_LIMIT:
            for table_key, _tp in sorted_tables:
                if table_key not in important_tables:
                    important_tables.append(table_key)
                if len(important_tables) >= DatabaseSummaryBuilder.IMPORTANT_TABLE_LIMIT:
                    break

        # Build common patterns
        common_patterns: list[str] = []
        fact_tables = [k for k, v in explorer.card.tables.items() if v.archetype == "fact"]
        dim_tables = [k for k, v in explorer.card.tables.items() if v.archetype == "dimension"]

        if fact_tables and dim_tables:
            common_patterns.append("Star schema: fact/dimension tables")
        if len(explorer.card.edges) > len(explorer.card.tables):
            common_patterns.append("Normalized: many relationships")
        if any(t.n_dates > 0 for t in explorer.card.tables.values()):
            common_patterns.append("Time-series: date columns")
        if any(t.n_metrics > 0 for t in explorer.card.tables.values()):
            common_patterns.append("Analytics: numeric metrics")

        return DatabaseSummary(
            database_type=explorer.card.db_dialect,
            total_tables=len(explorer.card.tables),
            schemas=list(explorer.card.schemas),
            key_subject_areas=key_subject_areas,
            subject_areas=subject_areas,
            most_important_tables=important_tables,
            common_patterns=common_patterns,
        )


class TableInfoBuilder:
    """Builder for TableInfo objects."""

    @staticmethod
    def build(
        table_key: str,
        explorer: SchemaExplorer,
        *,
        include_samples: bool,
        column_role_filter: list[str] | None = None,
        max_sample_values: int = 5,
        relationship_limit: int | None = None,
    ) -> TableInfo:
        """Build comprehensive table information.

        Args:
            table_key: Table identifier in 'schema.table' format
            explorer: SchemaExplorer instance with built schema card
            include_samples: Whether to include sample values

        Returns:
            TableInfo with comprehensive table details

        Raises:
            RuntimeError: If schema card is not available
            KeyError: If table not found
        """
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        table_profile = explorer.card.tables.get(table_key)
        if not table_profile:
            msg = f"Table '{table_key}' not found"
            raise KeyError(msg)

        # Build all components using helper methods
        columns = TableInfoBuilder._build_table_columns(
            table_profile,
            include_samples=include_samples,
            role_filter=column_role_filter,
            max_sample_values=max_sample_values,
        )
        relationships_all = TableInfoBuilder._build_table_relationships(table_key, explorer)
        relationships = (
            relationships_all[:relationship_limit]
            if relationship_limit is not None
            else relationships_all
        )
        typical_queries = TableInfoBuilder._build_typical_queries(
            table_key, table_profile, explorer
        )
        indexing_notes = TableInfoBuilder._build_indexing_notes(table_profile)

        return TableInfo(
            table_name=table_key,
            business_description=table_profile.summary
            or f"{table_profile.archetype or 'data'} table",
            columns=columns,
            relationships=relationships,
            typical_queries=typical_queries,
            indexing_notes=indexing_notes,
            pk_columns=list(table_profile.pk_cols),
            foreign_keys=[
                ForeignKeyRef(column=c, ref_table=rtab, ref_column=rcol)
                for c, rtab, rcol in table_profile.fks
            ],
            approx_rowcount=table_profile.approx_rowcount,
        )

    @staticmethod
    def _build_table_columns(
        table_profile: TableProfile,
        *,
        include_samples: bool,
        role_filter: list[str] | None,
        max_sample_values: int,
    ) -> list[ColumnDetail]:
        """Build column details for table information."""
        columns: list[ColumnDetail] = []
        for col in table_profile.columns:
            if role_filter and (col.role or "data") not in set(role_filter):
                continue
            # Get sample values if requested
            sample_values = []
            if include_samples and col.distinct_values:
                sample_values = [str(v) for v in col.distinct_values[:max_sample_values]]

            # Build constraints
            constraints: list[str] = []
            if col.distinct_values:
                constraints.append(
                    f"Values: {', '.join(str(v) for v in col.distinct_values[:max_sample_values])}"
                )
            if col.value_range:
                constraints.append(f"Range: {col.value_range[0]}-{col.value_range[1]}")

            # Determine business role
            business_role = col.role or "data"
            if col.is_pk:
                business_role = "primary key"
            elif col.is_fk:
                business_role = "foreign key"

            column_detail = ColumnDetail(
                name=col.name,
                data_type=_sanitize_sql_type(col.type),
                nullable=col.nullable,
                is_primary_key=col.is_pk,
                is_foreign_key=col.is_fk,
                business_role=business_role,
                sample_values=sample_values,
                constraints=constraints,
            )
            columns.append(column_detail)
        return columns

    @staticmethod
    def _build_table_relationships(table_key: str, explorer: SchemaExplorer) -> list[JoinExample]:
        """Build relationship examples for a table."""
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        relationships: list[JoinExample] = []
        for edge in explorer.card.edges:
            if edge[0] == table_key or edge[1] == table_key:
                relationship = TableInfoBuilder._create_table_relationship(
                    table_key, edge, explorer
                )
                if relationship:
                    relationships.append(relationship)
        return relationships

    @staticmethod
    def _create_table_relationship(
        table_key: str, edge: tuple[str, str, str], explorer: SchemaExplorer
    ) -> JoinExample | None:
        """Create a relationship example from an edge."""
        if not explorer.card:
            msg = "Schema card not available"
            raise RuntimeError(msg)

        # Determine direction
        from_table = edge[0]
        to_table = edge[1]

        # Parse FK description
        fk_desc = edge[2]
        if "->" not in fk_desc:
            return None

        parts = fk_desc.split("->")
        if len(parts) != FK_DESCRIPTION_PARTS_COUNT:
            return None

        from_parts = parts[0].split(".")
        to_parts = parts[1].split(".")
        if len(from_parts) < FK_TABLE_PARTS_MIN_COUNT or len(to_parts) < FK_TABLE_PARTS_MIN_COUNT:
            return None

        from_col = from_parts[-1]
        to_col = to_parts[-1]

        # Compile dialect-specific JOIN clause using SQLAlchemy
        sql_syntax = _compile_join_clause(from_table, to_table, from_col, to_col, explorer)

        # Get business purpose
        other_table = to_table if from_table == table_key else from_table
        other_profile = explorer.card.tables.get(other_table)
        other_archetype = other_profile.archetype if other_profile else "related"

        # Infer cardinality: if the current table is the FK side (from_table), it's many:1.
        # If current table is the referenced table (to_table), it's 1:many.
        relationship_type = "many:1" if table_key == from_table else "1:many"
        business_purpose = f"{relationship_type} → {other_archetype} ({other_table})"

        return JoinExample(
            from_table=from_table,
            to_table=to_table,
            sql_syntax=sql_syntax,
            relationship_type=relationship_type,
            business_purpose=business_purpose,
        )

    @staticmethod
    def _build_typical_queries(
        table_key: str, table_profile: TableProfile, explorer: SchemaExplorer
    ) -> list[str]:
        """Build typical query examples for a table using SQLAlchemy compilation."""
        typical_queries: list[str] = []

        # Helpers to construct lightweight selectable for table
        schema, name = table_key.split(".", 1)

        def table_with_cols(cols: list[str]) -> sa.TableClause:
            columns: list[Any] = [sa.column(c) for c in cols]
            return sa.table(name, *columns, schema=schema)  # pyright: ignore[reportUnknownArgumentType]

        # Metric aggregation example
        metric_cols = [c.name for c in table_profile.columns if c.role == "metric"]
        if metric_cols:
            mcol = metric_cols[0]
            t = table_with_cols([mcol])
            stmt = sa.select(sa.func.sum(t.c[mcol])).select_from(t)
            typical_queries.append(str(stmt.compile(dialect=explorer.dialect)))

        # Date filter example
        date_cols = [c.name for c in table_profile.columns if c.role == "date"]
        if date_cols:
            dcol = date_cols[0]
            t = table_with_cols([dcol])
            lit_all = cast(Any, sa.literal_column("*"))
            stmt = sa.select(lit_all).select_from(t).where(t.c[dcol] >= sa.bindparam("date_from"))  # pyright: ignore[reportUnknownArgumentType]
            typical_queries.append(str(stmt.compile(dialect=explorer.dialect)))

        # Lookup by PK example
        if table_profile.pk_cols:
            pk_col = table_profile.pk_cols[0]
            t = table_with_cols([pk_col])
            lit_all_pk = cast(Any, sa.literal_column("*"))
            stmt = sa.select(lit_all_pk).select_from(t).where(t.c[pk_col] == sa.bindparam("value"))  # pyright: ignore[reportUnknownArgumentType]
            typical_queries.append(str(stmt.compile(dialect=explorer.dialect)))

        return typical_queries

    @staticmethod
    def _build_indexing_notes(table_profile: TableProfile) -> list[str]:
        """Build indexing recommendation notes for a table."""
        indexing_notes: list[str] = []
        if table_profile.pk_cols:
            indexing_notes.append(f"PK index: {', '.join(table_profile.pk_cols)}")
        indexing_notes.extend(
            f"FK index: {col.name}" for col in table_profile.columns if col.is_fk
        )
        return indexing_notes


def _compile_join_clause(
    from_table_key: str,
    to_table_key: str,
    from_col: str,
    to_col: str,
    explorer: SchemaExplorer,
) -> str:
    """Compile a dialect-specific JOIN clause using SQLAlchemy.

    Builds lightweight table clauses with only the columns required for the ON condition,
    compiles the Join object against the active dialect, and returns the rendered SQL.
    """
    from_schema, from_name = from_table_key.split(".", 1)
    to_schema, to_name = to_table_key.split(".", 1)

    t_from = sa.table(from_name, sa.column(from_col), schema=from_schema)
    t_to = sa.table(to_name, sa.column(to_col), schema=to_schema)

    join_obj = t_from.join(t_to, t_from.c[from_col] == t_to.c[to_col])
    return str(join_obj.compile(dialect=explorer.dialect))


def _sanitize_sql_type(type_str: str) -> str:
    """Normalize SQL type strings for readability.

    Removes noisy collation clauses and quotes; uppercases type name while
    preserving precision/scale/length details.
    """
    s = type_str or ""
    # Strip collation clauses commonly seen on MSSQL
    upper = s.upper().split(" COLLATE ")[0].strip()
    # Remove stray double quotes
    upper = upper.replace('"', "")
    # Collapse spaces
    return " ".join(upper.split())
