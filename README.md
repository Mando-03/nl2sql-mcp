# nl2sql-mcp

A natural language to SQL Model Context Protocol (MCP) server that enables AI assistants to understand database schemas and generate SQL queries from natural language descriptions.

## Overview

This MCP server provides tools for:
- **Schema Discovery**: Automatically explore and understand database structures
- **Query Planning**: Generate optimized SQL queries from natural language
- **Flexible Database Support**: Works with various SQL databases through SQLAlchemy

The server is designed to be schema-agnostic and adaptable to different database environments without hardcoded assumptions.

## Features

- 🔍 **Intelligent Schema Analysis**: Discovers tables, columns, relationships, and constraints
- 🗣️ **Natural Language Processing**: Converts plain English to SQL queries
- 🎯 **Query Optimization**: Generates efficient, well-structured SQL
- 🔌 **Database Agnostic**: Supports multiple SQL databases via SQLAlchemy
- 🛡️ **Type Safety**: Built with strict type checking and validation
- 📊 **Vector Similarity**: Uses embeddings for intelligent schema matching

## Quick Start

### Prerequisites

- Python 3.13+
- uv (recommended) or pip
- Database drivers for your target database (e.g., pyodbc for SQL Server)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/jb3cloud/nl2sql-mcp.git
cd nl2sql-mcp
```

2. Install dependencies:
```bash
uv sync
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your database connection details
export NL2SQL_MCP_DATABASE_URL="your_database_url_here"
```

### Running the Server

```bash
# Using the entry point
uv run nl2sql-mcp

# Or directly
uv run python -m nl2sql_mcp.server
```

## Development

### Setup

```bash
# Install development dependencies
uv sync

# Run formatting
uv run ruff format .

# Run linting
uv run ruff check .

# Type checking
uv run basedpyright

# Run tests
uv run pytest -q
```

### Testing Intelligence Components

Use the harness script to test the intelligence components:

```bash
uv run python scripts/test_intelligence_harness.py
```

### Project Structure

- `src/nl2sql_mcp/`: Main package
  - `server.py`: FastMCP server implementation
  - `intelligence/`: AI/ML components for query generation
  - `services/`: Database and schema services
  - `builders/`: Query building utilities
- `scripts/`: Development and testing utilities
- `tests/`: Test suite (pytest)
- `docs/`: Documentation
- `examples/`: Usage examples and sample data

## Configuration

Set the following environment variable:

- `NL2SQL_MCP_DATABASE_URL`: Your database connection string

Examples:
```bash
# SQL Server
NL2SQL_MCP_DATABASE_URL="mssql+pyodbc://user:pass@server/database?driver=ODBC+Driver+17+for+SQL+Server"

# PostgreSQL
NL2SQL_MCP_DATABASE_URL="postgresql://user:pass@localhost/database"

# MySQL
NL2SQL_MCP_DATABASE_URL="mysql+pymysql://user:pass@localhost/database"
```

## Usage with AI Assistants

This MCP server integrates with AI assistants like Claude Desktop. Add it to your MCP configuration:

```json
{
  "mcpServers": {
    "nl2sql": {
      "command": "uv",
      "args": ["run", "nl2sql-mcp"],
      "env": {
        "NL2SQL_MCP_DATABASE_URL": "your_database_url"
      }
    }
  }
}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following the coding standards
4. Run the quality checks (`ruff`, `basedpyright`, `pytest`)
5. Commit your changes using Conventional Commits
6. Push to your branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Coding Standards

- Python 3.13 with strict type checking
- Follow PEP 8 with 99 character line limit
- Use double quotes for strings
- All public functions must have docstrings
- No hardcoded schema-specific logic
- Type hints are required

## Architecture

The server uses FastMCP to expose tools for:

1. **Schema Discovery**: Introspects database structure and relationships
2. **Query Planning**: Converts natural language to optimized SQL
3. **Semantic Matching**: Uses vector embeddings for intelligent schema mapping

Intelligence components are modular and testable, following dependency injection patterns.

## License

This project is licensed under the terms specified in the `pyproject.toml` file.

## Support

- Create an [issue](https://github.com/jb3cloud/nl2sql-mcp/issues) for bug reports or feature requests
- Check the [documentation](https://github.com/jb3cloud/nl2sql-mcp#readme) for usage examples
- Review the [changelog](https://github.com/jb3cloud/nl2sql-mcp/blob/main/CHANGELOG.md) for updates

---

Built with ❤️ using FastMCP and modern Python practices.