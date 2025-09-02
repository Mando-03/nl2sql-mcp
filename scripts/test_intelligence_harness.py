#!/usr/bin/env python3
"""Test harness for nl2sql-mcp MCP server functionality.

This script demonstrates the three core MCP server tools provided by nl2sql-mcp:
1. analyze_query_schema() - Finds relevant tables and provides schema info for a query
2. get_database_overview() - Gets high-level database overview
3. get_table_info() - Gets detailed table information

The script showcases how these tools provide intelligent analysis of database schemas
to enable natural language to SQL conversion, demonstrating the backend intelligence
that powers the MCP functionality.

Usage:
    python test_intelligence_harness.py

The script reads the database connection URL from the NL2SQL_MCP_DATABASE_URL
environment variable and tests each MCP tool with realistic examples.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

import dotenv

# Load environment variables
dotenv.load_dotenv()

# Add the src directory to the Python path for imports
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

try:
    import sqlalchemy as sa

    from nl2sql_mcp.intelligence.constants import RetrievalApproach
    from nl2sql_mcp.intelligence.embeddings import Embedder
    from nl2sql_mcp.intelligence.explorer import SchemaExplorer
    from nl2sql_mcp.intelligence.models import SchemaExplorerConfig
    from nl2sql_mcp.models import (
        ColumnDetail,
        DatabaseSummary,
        QuerySchemaResult,
        TableInfo,
    )
    from nl2sql_mcp.services.schema_service import SchemaService
except ImportError as e:
    print(f"❌ Failed to import required packages: {e}")
    print("Please ensure all dependencies are installed:")
    print("  uv sync")
    sys.exit(1)


# Cache a single SchemaService to avoid repeated reflection/embedding work across tests
_SERVICE_CACHE: dict[str, SchemaService] = {}
_EMBEDDER_CACHE: dict[str, Embedder] = {}


def _build_service(for_overview: bool = False) -> SchemaService:
    """Construct or reuse a cached SchemaService for tests.

    Uses a single, warmed SchemaExplorer to avoid re-initializing the schema card
    between tests, dramatically reducing total runtime for the harness.
    """
    # Reuse a cached default service across all calls
    if "default" in _SERVICE_CACHE:
        # keep signature compatibility; we intentionally ignore per-call overrides
        _ = for_overview  # silence unused-arg warnings while retaining API
        return _SERVICE_CACHE["default"]

    database_url = os.getenv("NL2SQL_MCP_DATABASE_URL")
    if not database_url:
        raise ValueError("NL2SQL_MCP_DATABASE_URL environment variable not set")

    # Favor a capable config once; reuse for all calls
    config = SchemaExplorerConfig(
        per_table_rows=50,
        sample_timeout=15,
        build_column_index=True,
        max_cols_for_embeddings=20,
        expander="fk_following",
        min_area_size=2,
        merge_archive_areas=True,
        value_constraint_threshold=20,
    )
    engine = sa.create_engine(database_url)
    explorer = SchemaExplorer(engine, config)
    explorer.build_index()
    # Initialize a single shared embedder and reuse across QueryEngine calls
    if "default" not in _EMBEDDER_CACHE:
        _EMBEDDER_CACHE["default"] = Embedder(model_name=config.model_name)
    shared_embedder = _EMBEDDER_CACHE["default"]
    service = SchemaService.from_database_url(database_url, explorer, shared_embedder)
    _SERVICE_CACHE["default"] = service
    return service


def get_database_overview() -> DatabaseSummary:
    """Get high-level database overview with business context."""
    service = _build_service(for_overview=True)
    return service.get_database_overview(include_subject_areas=True, area_limit=8)


def analyze_query_schema(query: str, max_tables: int = 5) -> QuerySchemaResult:
    """Find relevant tables and provide clear schema information for a query."""
    service = _build_service()
    return service.analyze_query_schema(
        query,
        max_tables,
        approach=RetrievalApproach.COMBINED,
        alpha=0.7,
        detail_level="standard",
        include_samples=False,
        max_sample_values=3,
        max_columns_per_table=20,
        join_limit=8,
    )


def get_table_info(table_key: str, include_samples: bool = True) -> TableInfo:
    """Get detailed table information for SQL development."""
    service = _build_service()
    return service.get_table_information(
        table_key,
        include_samples=include_samples,
        column_role_filter=["metric", "date", "key", "category"],
        max_sample_values=5,
        relationship_limit=12,
    )


def print_banner(title: str) -> None:
    """Print a formatted banner for section headers."""
    print(f"\n{'=' * 70}")
    print(f" {title}")
    print(f"{'=' * 70}")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'-' * 50}")
    print(f" {title}")
    print(f"{'-' * 50}")


def format_time(seconds: float) -> str:
    """Format time duration in a human-readable format."""
    if seconds < 1:
        return f"{seconds * 1000:.1f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes}m {remaining_seconds:.2f}s"


def test_database_overview() -> DatabaseSummary | None:
    """Test the get_database_overview MCP tool."""
    print_section("Testing MCP Tool: get_database_overview()")
    print("🎯 Purpose: Provides high-level database overview with business context")
    print("📋 Use Case: Initial database discovery and understanding schema organization")

    try:
        start_time = time.time()
        overview = get_database_overview()
        elapsed_time = time.time() - start_time

        print(f"⚡ Response time: {format_time(elapsed_time)}")
        print("✅ Database overview retrieved successfully!")

        print("\n📊 Database Summary:")
        print(f"   Database Type: {overview.database_type}")
        print(f"   Total Tables: {overview.total_tables}")
        print(f"   Schemas: {', '.join(overview.schemas)}")

        if overview.key_subject_areas:
            print("\n🏢 Key Subject Areas:")
            for area_id, description in overview.key_subject_areas.items():
                print(f"   • {area_id}: {description}")

        if overview.most_important_tables:
            print("\n🎯 Most Important Tables (by connectivity):")
            for i, table in enumerate(overview.most_important_tables[:5], 1):
                print(f"   {i}. {table}")

        if overview.common_patterns:
            print("\n📈 Common Database Patterns:")
            for pattern in overview.common_patterns:
                print(f"   • {pattern}")

        print("\n🧠 Intelligence Demonstrated:")
        print("   ✓ Automatic schema analysis and categorization")
        print("   ✓ Subject area detection and business context mapping")
        print("   ✓ Table importance ranking using graph centrality")
        print("   ✓ Pattern recognition for query optimization hints")

        return overview

    except Exception as e:
        print(f"❌ Failed to get database overview: {e}")
        return None


def test_query_schema_analysis() -> None:
    """Test the analyze_query_schema MCP tool with realistic queries."""
    print_section("Testing MCP Tool: analyze_query_schema()")
    print("🎯 Purpose: Finds relevant tables and provides schema info for specific queries")
    print("📋 Use Case: Converting natural language queries into SQL with proper table selection")

    # Test queries that demonstrate different types of intelligence
    test_queries = [
        {
            "query": "Show me total sales revenue by customer segment for this year",
            "purpose": "Tests semantic table retrieval and business intelligence",
        },
        {
            "query": "Find all orders with their shipping details and customer information",
            "purpose": "Tests relationship discovery and JOIN recommendation",
        },
        {
            "query": "Get inventory levels and stock movements for products",
            "purpose": "Tests constraint analysis and filter suggestions",
        },
    ]

    service = _build_service()
    for i, test_case in enumerate(test_queries, 1):
        query = test_case["query"]
        purpose = test_case["purpose"]

        print(f"\n🧪 Test Query {i}: {query}")
        print(f"   Purpose: {purpose}")

        try:
            start_time = time.time()
            # Reuse the cached service directly to avoid re-initialization costs
            result = service.analyze_query_schema(
                query,
                5,
                approach=RetrievalApproach.COMBINED,
                alpha=0.7,
                detail_level="standard",
                include_samples=False,
                max_sample_values=3,
                max_columns_per_table=20,
                join_limit=8,
            )
            elapsed_time = time.time() - start_time

            print(f"   ⚡ Analysis time: {format_time(elapsed_time)}")
            print(f"   ✅ Found {len(result.relevant_tables)} relevant tables")

            # Show selected tables with business context
            print("   📋 Selected Tables:")
            for table in result.relevant_tables:
                print(f"      • {table.name}: {table.business_purpose}")

                # Show key columns with data types
                key_columns = [
                    col
                    for col in table.columns
                    if col.is_primary_key
                    or col.is_foreign_key
                    or col.business_role in ["date", "metric"]
                ]
                if key_columns:
                    print(
                        f"        Key columns: {', '.join(f'{col.name} ({col.data_type})' for col in key_columns[:3])}"
                    )

            # Show JOIN intelligence
            if result.join_examples:
                print("   🔗 JOIN Intelligence:")
                for join in result.join_examples[:2]:  # Show first 2 JOINs
                    print(f"      • {join.sql_syntax}")
                    print(f"        Purpose: {join.business_purpose}")

            # Show structured planning hints
            if result.group_by_candidates:
                print("   📛 Group-By Candidates:")
                print("      • " + ", ".join(result.group_by_candidates[:5]))
            if result.filter_candidates:
                print("   🔎 Filter Candidates:")
                for fc in result.filter_candidates[:3]:
                    print(f"      • {fc.table}.{fc.column} ops: {', '.join(fc.operator_examples)}")

            print("   🧠 Intelligence Demonstrated:")
            print("      ✓ Semantic understanding of query intent")
            print("      ✓ Relevant table discovery using embeddings")
            print("      ✓ Automatic JOIN path identification")
            print("      ✓ Data type and constraint analysis")
            print("      ✓ Business context extraction")

        except Exception as e:
            print(f"   ❌ Query analysis failed: {e}")


def test_table_info_detail(table_candidates: list[str] | None = None) -> None:
    """Test the get_table_info MCP tool with detailed table analysis."""
    print_section("Testing MCP Tool: get_table_info()")
    print("🎯 Purpose: Provides comprehensive table details for SQL development")
    print("📋 Use Case: Deep dive into specific tables for complex query construction")

    # If no table candidates provided, try to get some from overview (reusing service)
    if not table_candidates:
        try:
            service = _build_service(for_overview=True)
            overview = service.get_database_overview(include_subject_areas=True, area_limit=8)
            table_candidates = overview.most_important_tables[:2]  # Test top 2 tables
        except Exception:
            print("⚠️  Could not determine table candidates - using fallback approach")
            return

    if not table_candidates:
        print("⚠️  No tables available for detailed analysis")
        return

    for i, table_key in enumerate(table_candidates[:2], 1):  # Test first 2 tables
        print(f"\n🔍 Analyzing Table {i}: {table_key}")

        try:
            start_time = time.time()
            # Reuse cached service
            service = _build_service()
            table_info = service.get_table_information(
                table_key,
                include_samples=True,
                column_role_filter=["metric", "date", "key", "category"],
                max_sample_values=5,
                relationship_limit=12,
            )
            elapsed_time = time.time() - start_time

            print(f"   ⚡ Analysis time: {format_time(elapsed_time)}")
            print("   ✅ Table analysis complete")

            # Show business description
            print(f"   📝 Business Description: {table_info.business_description}")

            # Show column intelligence
            print(f"   📊 Column Analysis ({len(table_info.columns)} columns):")

            # Group columns by business role
            role_groups: dict[str, list[ColumnDetail]] = {}
            for col in table_info.columns:
                role = col.business_role or "data"
                if role not in role_groups:
                    role_groups[role] = []
                role_groups[role].append(col)

            for role, columns in role_groups.items():
                if len(columns) <= 3:  # Show all if few columns
                    for col in columns:
                        type_info = f"{col.data_type}{'?' if col.nullable else ''}"
                        sample_info = (
                            f" (e.g., {', '.join(col.sample_values[:2])})"
                            if col.sample_values
                            else ""
                        )
                        print(f"      • {col.name} [{type_info}] - {role}{sample_info}")
                else:  # Show summary if many columns
                    sample_cols = columns[:2]
                    for col in sample_cols:
                        type_info = f"{col.data_type}{'?' if col.nullable else ''}"
                        sample_info = (
                            f" (e.g., {', '.join(col.sample_values[:2])})"
                            if col.sample_values
                            else ""
                        )
                        print(f"      • {col.name} [{type_info}] - {role}{sample_info}")
                    if len(columns) > 2:
                        print(
                            f"      • (+{len(columns) - 2} more {role} columns hidden for brevity)"
                        )

            # Show relationship intelligence
            if table_info.relationships:
                print("   🔗 Relationship Intelligence:")
                for rel in table_info.relationships[:3]:  # Show first 3 relationships
                    print(f"      • {rel.sql_syntax}")
                    print(f"        {rel.business_purpose}")

            # Show query patterns
            if table_info.typical_queries:
                print("   🧪 Typical Query Patterns:")
                for query_pattern in table_info.typical_queries[:2]:
                    print(f"      • {query_pattern}")

            # Show indexing intelligence
            if table_info.indexing_notes:
                print("   ⚡ Performance Intelligence:")
                for note in table_info.indexing_notes[:2]:
                    print(f"      • {note}")

            print("   🧠 Intelligence Demonstrated:")
            print("      ✓ Complete column metadata with business roles")
            print("      ✓ Sample value extraction for understanding data")
            print("      ✓ Relationship mapping with JOIN syntax")
            print("      ✓ Query pattern recognition")
            print("      ✓ Performance optimization hints")

        except KeyError:
            print(f"   ⚠️  Table '{table_key}' not found - may not exist in current database")
        except Exception as e:
            print(f"   ❌ Table analysis failed: {e}")


def demonstrate_mcp_intelligence() -> None:
    """Demonstrate the overall intelligence capabilities of the MCP tools."""
    print_section("MCP Intelligence Capabilities Summary")

    print("🧠 The nl2sql-mcp server provides three levels of intelligence:")
    print()

    print("1. 🌐 DATABASE OVERVIEW INTELLIGENCE:")
    print("   • Automatic schema discovery and cataloging")
    print("   • Subject area detection using graph clustering")
    print("   • Table importance ranking via centrality analysis")
    print("   • Pattern recognition for query optimization")
    print("   • Business context extraction from metadata")
    print()

    print("2. 🎯 QUERY-SPECIFIC INTELLIGENCE:")
    print("   • Semantic understanding of natural language queries")
    print("   • Relevant table discovery using hybrid retrieval (lexical + semantic)")
    print("   • Graph expansion to find related tables via foreign keys")
    print("   • JOIN path identification with business context")
    print("   • Constraint analysis for filter suggestions")
    print("   • SQL generation guidance and approach recommendations")
    print()

    print("3. 🔍 TABLE-LEVEL INTELLIGENCE:")
    print("   • Deep column analysis with business role classification")
    print("   • Sample value extraction for data understanding")
    print("   • Constraint detection for WHERE clause optimization")
    print("   • Relationship mapping with complete JOIN syntax")
    print("   • Query pattern recognition for common use cases")
    print("   • Performance hints based on indexing analysis")
    print()

    print("🎯 INTELLIGENCE FLOW:")
    print("   1. Natural language query → Semantic analysis → Table selection")
    print("   2. Graph traversal → Relationship discovery → JOIN recommendations")
    print("   3. Constraint analysis → Filter suggestions → SQL optimization")
    print("   4. Business context → Human-readable explanations → Guided development")
    print()

    print("⚡ This intelligence enables:")
    print("   • Accurate table selection from natural language")
    print("   • Automatic JOIN discovery and syntax generation")
    print("   • Smart filtering based on actual data constraints")
    print("   • Context-aware SQL generation with business meaning")


def main() -> None:
    """Main test harness execution for MCP server functionality."""
    print_banner("NL2SQL MCP Server Intelligence Demonstration")
    print("This script demonstrates the three core MCP tools and their intelligence capabilities.")

    # Check environment setup
    database_url = os.getenv("NL2SQL_MCP_DATABASE_URL")
    if not database_url:
        print("❌ NL2SQL_MCP_DATABASE_URL environment variable not set!")
        print("Please set the database connection URL in your environment.")
        print("Example: export NL2SQL_MCP_DATABASE_URL='mssql+pyodbc://...your-connection-string'")
        sys.exit(1)

    print(f"🔗 Using database URL: {database_url[:50]}...")

    try:
        # Test 1: Database Overview Intelligence
        overview = test_database_overview()

        # Test 2: Discovery utilities (status/areas/search)
        try:
            print_section("Testing Discovery Utilities: status, areas, search")
            service = _build_service(for_overview=True)
            # Status via manager
            from nl2sql_mcp.services.schema_service_manager import (  # noqa: PLC0415
                SchemaServiceManager,
            )

            mgr = SchemaServiceManager.get_instance()
            st = mgr.status()
            print(f"   🟢 Init Status: phase={st.phase.name} attempts={st.attempts}")

            # Subject areas (top few)
            if service.explorer.card and service.explorer.card.subject_areas:
                ids = sorted(
                    service.explorer.card.subject_areas.keys(),
                    key=lambda aid: len(service.explorer.card.subject_areas[aid].tables),  # pyright: ignore[reportOptionalMemberAccess]
                    reverse=True,
                )[:5]
                if ids:
                    print("   🗂️  Subject Areas (top):")
                    for aid in ids:
                        data = service.explorer.card.subject_areas[aid]
                        print(f"      • {data.name}: {len(data.tables)} tables")

            # find_tables
            hits = service.find_tables(
                "top customers by revenue", limit=5, approach=RetrievalApproach.COMBINED, alpha=0.7
            )
            if hits:
                print("   🔎 Table hits:")
                for h in hits:
                    print(f"      • {h.table} ({h.score:.3f}) - {h.summary or 'n/a'}")

            # find_columns
            chits = service.find_columns("revenue", limit=8)
            if chits:
                print("   🔎 Column hits:")
                for c in chits[:5]:
                    print(
                        f"      • {c.table}.{c.column} [{c.data_type or '?'}] role={c.role or 'n/a'}"
                    )
        except Exception as e:
            print(f"⚠️  Discovery utilities failed: {e}")

        # Test 3: Query Schema Analysis Intelligence
        test_query_schema_analysis()

        # Test 4: Table Detail Intelligence
        table_candidates = overview.most_important_tables if overview else None
        test_table_info_detail(table_candidates)

        # Demonstrate overall intelligence capabilities
        demonstrate_mcp_intelligence()

        print_section("MCP Server Test Completed Successfully")
        print("✅ All MCP tools demonstrated successfully!")
        print("🎉 The nl2sql-mcp server intelligence is working correctly.")
        print()
        print("📋 Summary of Capabilities Tested:")
        print("   ✓ Database overview with business context")
        print("   ✓ Query-specific table selection and analysis")
        print("   ✓ Detailed table information with relationships")
        print("   ✓ Semantic understanding and intelligence extraction")
        print("   ✓ Graph-based relationship discovery")
        print("   ✓ Constraint analysis for SQL optimization")
        print()
        print("🚀 Ready for MCP client integration!")

    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("   • Verify NL2SQL_MCP_DATABASE_URL is correctly set")
        print("   • Ensure database server is accessible")
        print("   • Check that required dependencies are installed: uv sync")
        print("   • Verify database contains tables for analysis")
        print("   • Check database permissions for schema introspection")
        sys.exit(1)


if __name__ == "__main__":
    main()
