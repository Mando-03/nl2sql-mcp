"""Custom exception hierarchy for SchemaExplorer.

This module defines all custom exceptions used throughout the schema exploration
system. The exception hierarchy provides specific error types for different
operational failures, making it easier to handle specific error conditions
and provide meaningful error messages to users.

Exception Categories:
- Base exceptions for general schema exploration errors
- Reflection errors for database schema reflection failures
- Sampling errors for data sampling operation failures
- Embedding errors for semantic embedding operation failures
"""

from __future__ import annotations


class SchemaExplorerError(Exception):
    """Base exception for SchemaExplorer operations.

    This is the root exception class for all schema exploration related errors.
    All other custom exceptions in this module inherit from this class.
    """


class ReflectionError(SchemaExplorerError):
    """Raised when database schema reflection fails.

    This exception is raised when the system cannot successfully reflect
    database schema information, such as when:
    - Database connection fails
    - Schema or table access is denied
    - Metadata retrieval encounters errors
    - SQL dialect specific reflection issues occur
    """


class SamplingError(SchemaExplorerError):
    """Raised when table sampling operations fail.

    This exception is raised when the system cannot successfully sample
    data from database tables, such as when:
    - Query execution fails due to permissions or syntax errors
    - Timeout occurs during data sampling
    - Table does not exist or is inaccessible
    - Data type conversion issues during sampling
    """


class EmbeddingError(SchemaExplorerError):
    """Raised when embedding operations fail.

    This exception is raised when semantic embedding operations encounter
    errors, such as when:
    - Embedding model fails to load or initialize
    - Text encoding operations fail
    - Vector similarity search operations fail
    - Memory issues with large embedding operations
    """
