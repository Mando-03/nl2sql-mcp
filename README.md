# nl2sql-mcp

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![Type Checked](https://img.shields.io/badge/type--checked-basedpyright-blue.svg)](https://github.com/detachhead/basedpyright)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A production-ready **Model Context Protocol (MCP) server** that transforms natural language into safe, executable SQL queries. Built for LLMs with comprehensive type safety, multi-database support, and intelligent schema analysis.

## Database Support

This project provides an "all drivers" container image that can connect to the major databases without post-build steps. Drivers are modeled as optional dependencies and the Dockerfile installs the minimal OS libraries required at runtime.

- PostgreSQL: Python driver `psycopg[binary]` (v3); OS libs: `libpq5`.
- MySQL/MariaDB: Python driver `mysqlclient`; OS libs: `libmariadb3`.
- SQL Server: Python driver `pyodbc`; OS libs: `unixodbc`, Microsoft `msodbcsql18` (+ optional `mssql-tools18`).
- SQLite: stdlib `sqlite3` (no extra OS libs).

Local dev installs:

- All drivers: `uv sync --extra drivers-all`
- Specific backends: `uv sync --extra postgres --extra mysql` (as needed)

Build the all-drivers image:

```
docker build -t nl2sql-mcp:drivers-all .
docker run --rm -p 8000:8000 nl2sql-mcp:drivers-all
```

Notes:

- Debian slim base maximizes prebuilt wheel compatibility. Avoid Alpine for DB stacks.
- To switch MySQL to a pure-Python driver, replace `mysqlclient` with `mysql-connector-python` in `pyproject.toml` and re-lock with `uv lock --extra drivers-all`.

## 🚀 Key Features

### 🎯 **LLM-Optimized Intelligence**
- **Intent-first query planning** with structured schema context and join recommendations
- **Semantic schema analysis** with automatic table classification (fact, dimension, bridge, reference)
- **Multi-modal table discovery** using lexical matching, embeddings, and graph traversal
- **Column role detection** (key, date, metric, category) with semantic tagging

### 🛡️ **Production-Ready Safety**
- **SELECT-only execution** with comprehensive SQL validation
- **Dialect normalization** and transpilation via SQLGlot
- **Row limits and cell truncation** to prevent resource exhaustion
- **Comprehensive error handling** with actionable feedback

### 🔧 **Multi-Database Support**
- **SQLAlchemy-powered** compatibility with PostgreSQL, MySQL, SQL Server, SQLite, Oracle, Snowflake
- **Dialect-aware** SQL generation and optimization
- **Cross-platform** schema reflection and analysis

### 🏗️ **Enterprise Architecture**
- **Type-safe** Pydantic models throughout
- **Dependency injection** for testability
- **Background initialization** with graceful degradation
- **Zero hardcoded assumptions** - adapts to any database schema

## 📦 Quick Start

### Prerequisites

- **Python 3.13+**
- **uv** package manager
- Database with appropriate drivers installed

### Installation

```bash
# Clone the repository
git clone https://github.com/jb3cloud/nl2sql-mcp.git
cd nl2sql-mcp

# Install dependencies
uv sync

# Configure your database
cp .env.example .env
# Edit .env with your database connection details
```

### Basic Usage

```bash
# Start the MCP server
uv run nl2sql-mcp

# Or run directly
uv run python -m nl2sql_mcp.server
```

### Environment Configuration

Create a `.env` file with your database connection:

```bash
# Required: Database connection
NL2SQL_MCP_DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Optional: Result limits and debugging
NL2SQL_MCP_ROW_LIMIT=1000
NL2SQL_MCP_MAX_CELL_CHARS=500
NL2SQL_MCP_DEBUG_TOOLS=1  # Enable find_tables/find_columns tools
```

## 🏛️ Architecture

```mermaid
graph TD
    A[LLM Client] -->|MCP Protocol| B[FastMCP Server]

    subgraph "Core Services"
        B --> C[Schema Service]
        B --> D[SQLGlot Service]
        B --> E[Execution Engine]
    end

    subgraph "Intelligence Layer"
        C --> F[Schema Explorer]
        C --> G[Query Engine]
        F --> H[Reflection & Profiling]
        F --> I[Graph Analysis]
        G --> J[Multi-Modal Retrieval]
        G --> K[Graph Expansion]
    end

    subgraph "Data Layer"
        E --> L[SQLAlchemy Engine]
        H --> L
        L --> M[(Your Database)]
    end

    style A fill:#e1f5fe
    style B fill:#f3e5f5
    style M fill:#e8f5e8
```

The system follows a **two-phase architecture**:

1. **Schema Building Phase**: Comprehensive database analysis, relationship mapping, and semantic understanding
2. **Query Processing Phase**: Real-time natural language to SQL conversion with context-aware planning

## 🔌 MCP Tools API

### Core Workflow Tools

#### `get_init_status()`
Check server readiness and initialization progress.

```json
// Response
{
  "phase": "READY",
  "attempts": 1,
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:30:45Z"
}
```

#### `get_database_overview(req: DatabaseOverviewRequest)`
High-level database summary with subject areas.

```json
// Request
{
  "include_subject_areas": true,
  "area_limit": 8
}

// Response
{
  "total_tables": 45,
  "total_schemas": 3,
  "subject_areas": [
    {
      "name": "Sales Analytics",
      "tables": ["orders", "customers", "products"],
      "summary": "Customer orders and product sales data"
    }
  ]
}
```

#### `plan_query_for_intent(req: PlanQueryRequest)`
Intent-first SQL planning with structured guidance.

```json
// Request
{
  "request": "Show monthly revenue by region for 2024",
  "constraints": {
    "time_range": "2024-01-01..2024-12-31",
    "metric": "revenue"
  },
  "detail_level": "standard"
}

// Response
{
  "relevant_tables": [
    {
      "table_key": "sales.orders",
      "relevance_score": 0.95,
      "why_relevant": "Contains revenue data and date columns"
    }
  ],
  "join_plan": [
    ["sales.orders.customer_id", "customers.id"]
  ],
  "main_table": "sales.orders",
  "draft_sql": "SELECT DATE_TRUNC('month', order_date) as month...",
  "confidence": 0.92
}
```

#### `execute_query(req: ExecuteQueryRequest)`
Safe SQL execution with validation and results.

```json
// Request
{
  "sql": "SELECT region, SUM(amount) as revenue FROM sales.orders WHERE order_date >= '2024-01-01' GROUP BY region"
}

// Response
{
  "success": true,
  "rows": [
    {"region": "North", "revenue": 125000.50},
    {"region": "South", "revenue": 98750.25}
  ],
  "row_count": 2,
  "columns": [
    {"name": "region", "type": "VARCHAR"},
    {"name": "revenue", "type": "DECIMAL"}
  ],
  "execution_time_ms": 45,
  "next_action": "success"
}
```

### Discovery Tools

#### `get_table_info(req: TableInfoRequest)`
Detailed table metadata optimized for SQL generation.

```json
// Request
{
  "table_key": "sales.orders",
  "include_samples": true,
  "column_role_filter": ["key", "date", "metric"]
}
```

#### `find_tables(req: FindTablesRequest)` *(Debug Mode)*
Fast table discovery by natural language intent.

#### `find_columns(req: FindColumnsRequest)` *(Debug Mode)*
Column search for SELECT and WHERE clause building.

### SQL Assistance Tools

#### `sql_validate(sql: str)`
Validate SQL syntax and structure.

#### `sql_auto_transpile_for_database(sql: str)`
Automatically detect and convert SQL dialects.

#### `sql_optimize_for_database(sql: str)`
Optimize SQL for your database engine.

## ⚙️ Configuration

### Database Support

| Database | SQLAlchemy Driver | Connection String Example |
|----------|-------------------|---------------------------|
| PostgreSQL | `psycopg2` | `postgresql://user:pass@host:5432/db` |
| MySQL | `pymysql` | `mysql+pymysql://user:pass@host:3306/db` |
| SQL Server | `pyodbc` | `mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+17` |
| SQLite | Built-in | `sqlite:///path/to/database.db` |
| Oracle | `cx_oracle` | `oracle://user:pass@host:1521/service` |
| Snowflake | `snowflake-sqlalchemy` | `snowflake://user:pass@account/db/schema` |

### Schema Configuration

Control schema analysis behavior:

```python
# Via environment or configuration
NL2SQL_MCP_INCLUDE_SCHEMAS=public,analytics
NL2SQL_MCP_EXCLUDE_SCHEMAS=temp,audit
NL2SQL_MCP_SAMPLE_SIZE=100  # Rows per table for profiling
```

### Performance Tuning

```bash
# Memory and processing limits
NL2SQL_MCP_ROW_LIMIT=1000           # Max rows returned
NL2SQL_MCP_MAX_CELL_CHARS=500       # Truncate long text
NL2SQL_MCP_SAMPLE_TIMEOUT=5         # Sampling timeout (seconds)
NL2SQL_MCP_MAX_COLS_FOR_EMBEDDINGS=20  # Column embedding limit
```

## 🧪 Testing and Development

### Local Development Setup

```bash
# Install development dependencies
uv sync --dev

# Run type checking
uv run basedpyright

# Format and lint code
uv run ruff format .
uv run ruff check --fix .

# Run tests
uv run pytest -v
```

### Testing with Live Database

```bash
# Schema intelligence testing
uv run python scripts/test_intelligence_harness.py "show sales by region"

# SQL tools testing
uv run python scripts/test_sqlglot_harness.py "SELECT TOP 10 * FROM customers"
```

### Quality Assurance

- **100% type coverage** with basedpyright strict mode
- **Comprehensive test suite** with pytest
- **Zero linting violations** with ruff
- **Dependency injection** for testability
- **Pure functions** where possible

## 📚 Advanced Usage

### Custom Schema Analysis

```python
from nl2sql_mcp.services import ConfigService, SchemaServiceManager

# Initialize with custom configuration
config = ConfigService()
manager = SchemaServiceManager.get_instance()

# Access schema service after initialization
schema_service = manager.get_schema_service()
result = schema_service.analyze_query_schema(
    "Find customers with high lifetime value",
    max_tables=10,
    expand_strategy="fk_following"
)
```

### Multi-Agent Integration

The MCP server integrates seamlessly with multi-agent frameworks:

```python
# Example with your LLM framework
async def query_database(natural_language_query: str):
    # 1. Plan the query
    plan_result = await mcp_client.call_tool(
        "plan_query_for_intent",
        {"request": natural_language_query}
    )

    # 2. Execute the draft SQL
    if plan_result.draft_sql:
        execution_result = await mcp_client.call_tool(
            "execute_query",
            {"sql": plan_result.draft_sql}
        )
        return execution_result.rows
```

### Code Standards

- **Python 3.13+** with strict type checking
- **Pydantic models** for all data structures
- **Pure functions** and dependency injection for testability
- **Comprehensive docstrings** for public APIs
- **Zero tolerance** for type errors, lint violations, or test failures

## 🏢 Production Deployment

### Environment Variables

```bash
# Required
NL2SQL_MCP_DATABASE_URL=postgresql://...

# Optional performance tuning
NL2SQL_MCP_ROW_LIMIT=5000
NL2SQL_MCP_MAX_CELL_CHARS=1000
NL2SQL_MCP_SAMPLE_SIZE=200
```

### Health Monitoring

Monitor server health via the `get_init_status()` tool:

- `READY`: Server fully operational
- `STARTING`: Initialization in progress
- `FAILED`: Initialization failed, check logs

## 📖 Related Research

This implementation incorporates state-of-the-art research in text-to-SQL:

- **Multi-agent architectures** for complex query decomposition
- **Schema linking** with bidirectional context understanding
- **Error correction frameworks** with multi-turn refinement
- **Semantic understanding** via lightweight NER and role classification

For detailed research context, see [NL2SQL_RESEARCH.md](docs/NL2SQL_RESEARCH.md).

## 🙏 Acknowledgments

- **[FastMCP](https://gofastmcp.com)** for the excellent MCP server framework
- **[SQLGlot](https://sqlglot.com)** for multi-dialect SQL parsing and transpilation
- **[SQLAlchemy](https://sqlalchemy.org)** for robust database abstraction
- The **text-to-SQL research community** for advancing the field
