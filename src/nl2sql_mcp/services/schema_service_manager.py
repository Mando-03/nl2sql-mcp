"""Schema service manager for nl2sql-mcp.

Provides a singleton `SchemaService` with background initialization during
FastMCP lifespan. Ensures exactly-once startup per process, fast-fails while
initializing, and keeps global explorer/embedder as singletons.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
import hashlib
import threading
import time
from typing import ClassVar

from fastmcp.utilities.logging import get_logger
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from nl2sql_mcp.schema_tools.embeddings import Embedder
from nl2sql_mcp.schema_tools.explorer import SchemaExplorer
from nl2sql_mcp.services.config_service import ConfigService
from nl2sql_mcp.services.schema_service import SchemaService
from nl2sql_mcp.services.state import (
    INIT_NOT_READY_PHASES,
    SchemaInitPhase,
    SchemaInitState,
)


class SchemaServiceManager:
    """Singleton manager for SchemaService instances.

    This manager ensures that SchemaService is initialized once during
    FastMCP lifespan startup and provides thread-safe access throughout
    the session lifecycle.
    """

    _instance: ClassVar[SchemaServiceManager | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    GLOBAL_EXPLORER: ClassVar[SchemaExplorer | None] = None
    GLOBAL_EMBEDDER: ClassVar[Embedder | None] = None

    def __init__(self) -> None:
        """Initialize the schema service manager."""
        self._schema_service: SchemaService | None = None
        self._initialization_lock = asyncio.Lock()
        self._logger = get_logger(__name__)
        self._sa_dialect_name: str | None = None

        # Background thread and state
        self._thread_lock = threading.Lock()
        self._init_thread: threading.Thread | None = None
        self._thread_ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._state = SchemaInitState(phase=SchemaInitPhase.IDLE)

    @classmethod
    def get_instance(cls) -> SchemaServiceManager:
        """Get the singleton instance of SchemaServiceManager.

        Returns:
            SchemaServiceManager: The singleton instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for testing)."""
        with cls._lock:
            cls._instance = None

    def start_background_initialization(self) -> None:
        """Start background initialization exactly once without blocking."""
        with self._thread_lock:
            if self._state.phase in {
                SchemaInitPhase.STARTING,
                SchemaInitPhase.RUNNING,
                SchemaInitPhase.READY,
            }:
                self._logger.debug("Initialization already %s; skipping start", self._state.phase)
                return
            if self._state.phase in {SchemaInitPhase.FAILED, SchemaInitPhase.STOPPED}:
                # Do not auto-restart after failure or stop
                self._logger.warning(
                    "Initialization in phase %s; not restarting", self._state.phase
                )
                return

            self._state = replace(
                self._state, phase=SchemaInitPhase.STARTING, started_at=time.time()
            )
            self._thread_ready.clear()
            self._loop = asyncio.get_running_loop()

            def _runner() -> None:
                self._state = replace(self._state, phase=SchemaInitPhase.RUNNING)
                try:
                    self._initialize_sync()
                except (ValueError, RuntimeError, OSError, SQLAlchemyError) as exc:
                    self._state = replace(
                        self._state,
                        phase=SchemaInitPhase.FAILED,
                        error_message=str(exc),
                        completed_at=time.time(),
                        attempts=self._state.attempts + 1,
                    )
                    self._logger.exception("SchemaService initialization failed")
                else:
                    self._state = replace(
                        self._state,
                        phase=SchemaInitPhase.READY,
                        completed_at=time.time(),
                        attempts=self._state.attempts + 1,
                    )
                finally:
                    self._thread_ready.set()
                    if self._loop is not None:
                        with contextlib.suppress(RuntimeError):
                            self._loop.call_soon_threadsafe(lambda: None)

            self._init_thread = threading.Thread(target=_runner, name="schema-init", daemon=True)
            self._init_thread.start()

    async def initialize(self) -> None:
        """Await until initialization completes (READY or FAILED)."""
        self.start_background_initialization()
        await self.ensure_ready(wait_timeout=None)

    async def ensure_ready(self, wait_timeout: float | None = None) -> bool:
        """Wait for initialization completion.

        Returns True when READY. Returns False on timeout or FAILED.
        """
        phase = self._state.phase
        if phase is SchemaInitPhase.READY:
            return True
        if phase is SchemaInitPhase.FAILED:
            return False
        await asyncio.to_thread(self._thread_ready.wait, wait_timeout)
        return self._state.phase is SchemaInitPhase.READY

    def _ensure_global_explorer(self, engine: sa.Engine) -> None:
        """Build the global schema explorer if needed.

        Args:
            engine: SQLAlchemy engine to use for reflection
        """
        if type(self).GLOBAL_EXPLORER is None:
            self._logger.info("Building global schema explorer (cold start may take seconds)…")
            config = ConfigService.get_query_analysis_config()
            global_explorer = SchemaExplorer(engine, config)
            global_explorer.build_index()
            if not global_explorer.card:
                msg = "Failed to build schema card"
                raise RuntimeError(msg)
            type(self).GLOBAL_EXPLORER = global_explorer
            self._logger.info("Global schema explorer built successfully")
        else:
            self._logger.info("Using existing global schema explorer")

    def _ensure_global_embedder(self) -> None:
        """Build the global embedder if needed."""
        if type(self).GLOBAL_EMBEDDER is None:
            self._logger.info("Building global embedder…")
            config = ConfigService.get_query_analysis_config()
            try:
                global_embedder = Embedder(model_name=config.model_name)
                type(self).GLOBAL_EMBEDDER = global_embedder
                self._logger.info("Global embedder built with model: %s", config.model_name)
            except RuntimeError as e:
                self._logger.warning("Embeddings disabled: %s", e)
                type(self).GLOBAL_EMBEDDER = None
        else:
            self._logger.info("Using existing global embedder")

    async def get_schema_service(self) -> SchemaService:
        """Get the initialized SchemaService instance.

        Returns:
            SchemaService: The initialized schema service instance

        Raises:
            RuntimeError: If the service is not initialized or initialization failed
        """
        phase = self._state.phase
        if phase in INIT_NOT_READY_PHASES:
            self._logger.info("SchemaService requested while initializing (phase=%s)", phase)
            msg = "SchemaService initialization in progress"
            raise RuntimeError(msg)
        if phase is SchemaInitPhase.FAILED:
            self._logger.error(
                "SchemaService initialization previously failed: %s", self._state.error_message
            )
            msg = "SchemaService is not available due to initialization failure"
            raise RuntimeError(msg)
        if phase is SchemaInitPhase.STOPPED:
            self._logger.error("SchemaService requested after STOPPED phase")
            msg = "SchemaService has been stopped"
            raise RuntimeError(msg)

        if self._schema_service is None:
            self._logger.error("SchemaService instance is None despite successful initialization")
            error_msg = "SchemaService instance is unexpectedly None"
            raise RuntimeError(error_msg)

        self._logger.debug("Retrieved SchemaService singleton instance")
        return self._schema_service

    async def shutdown(self) -> None:
        """Shutdown the SchemaService and clean up resources."""
        async with self._initialization_lock:
            if self._schema_service is not None:
                try:
                    self._logger.info("Shutting down SchemaService…")

                    # Dispose of the database engine
                    if hasattr(self._schema_service, "engine"):
                        self._schema_service.engine.dispose()
                        self._logger.debug("Database engine disposed")

                    self._schema_service = None
                    self._logger.info("SchemaService shutdown completed")

                except (AttributeError, OSError, RuntimeError) as exc:
                    self._logger.warning("Error during SchemaService shutdown: %s", exc)
                finally:
                    self._state = replace(self._state, phase=SchemaInitPhase.STOPPED)

    @property
    def is_initialized(self) -> bool:
        """Check if the SchemaService is initialized.

        Returns:
            bool: True if initialized, False otherwise
        """
        return self._state.phase is SchemaInitPhase.READY

    @property
    def has_initialization_error(self) -> bool:
        """Check if there was an initialization error.

        Returns:
            bool: True if there was an error, False otherwise
        """
        return self._state.phase is SchemaInitPhase.FAILED

    def status(self) -> SchemaInitState:
        """Return a snapshot of the initialization state."""
        return self._state

    # Public helper for consumers that need the active SQLAlchemy dialect name
    def current_sqlalchemy_dialect_name(self) -> str | None:
        """Return the current SQLAlchemy dialect name if initialized."""
        return self._sa_dialect_name

    # ---- internal ------------------------------------------------------------

    def _initialize_sync(self) -> None:
        """Perform synchronous initialization work. Runs in background thread."""
        self._logger.info("Starting SchemaService initialization…")

        # Get database URL from environment
        database_url = ConfigService.get_database_url()
        fp = hashlib.sha256(database_url.encode("utf-8")).hexdigest()[:10]
        self._logger.debug("Using database fingerprint: %s", fp)

        # Create database engine
        engine = ConfigService.create_database_engine(database_url)
        # Record dialect name for external consumers
        try:
            self._sa_dialect_name = engine.dialect.name  # e.g., 'postgresql'
        except Exception:  # noqa: BLE001 - defensive
            self._sa_dialect_name = None

        # Test database connectivity
        self._logger.debug("Testing database connectivity…")
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))

        # Ensure global explorer is available; defer embedder until first use
        self._ensure_global_explorer(engine)

        # Create SchemaService instance with the global explorer and embedder
        global_explorer = type(self).GLOBAL_EXPLORER
        if global_explorer is None:
            msg = "Global explorer is unexpectedly None"
            raise RuntimeError(msg)

        global_embedder = type(self).GLOBAL_EMBEDDER
        self._schema_service = SchemaService(engine, global_explorer, global_embedder)
        self._logger.info("SchemaService instance created successfully")
