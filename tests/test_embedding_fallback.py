"""Tests for graceful fallback when embeddings cannot be initialized.

Ensures QueryEngine disables embeddings and continues with lexical retrieval
when the embedding backend cannot be created (e.g., invalid model path).
"""

from __future__ import annotations

from _pytest.monkeypatch import MonkeyPatch

from nl2sql_mcp.models import SubjectAreaData
from nl2sql_mcp.schema_tools import query_engine as qe_mod
from nl2sql_mcp.schema_tools.models import (
    ColumnProfile,
    SchemaCard,
    SchemaExplorerConfig,
    TableProfile,
)


def _dummy_card() -> SchemaCard:
    """Create a minimal SchemaCard suitable for QueryEngine construction."""
    tables: dict[str, TableProfile] = {
        "sales.orders": TableProfile(
            schema="sales",
            name="orders",
            columns=[
                ColumnProfile(name="order_id", type="int", nullable=False, is_pk=True),
                ColumnProfile(name="order_date", type="date", nullable=False),
                ColumnProfile(name="amount", type="numeric", nullable=False),
            ],
            fks=[],
            pk_cols=["order_id"],
            summary="Customer orders including amounts and dates",
        ),
        "sales.customers": TableProfile(
            schema="sales",
            name="customers",
            columns=[
                ColumnProfile(name="customer_id", type="int", nullable=False, is_pk=True),
                ColumnProfile(name="name", type="text", nullable=False),
            ],
            fks=[],
            pk_cols=["customer_id"],
            summary="Customer master records",
        ),
    }

    return SchemaCard(
        db_dialect="sqlite",
        db_url_fingerprint="deadbeef",
        schemas=["sales"],
        subject_areas={"0": SubjectAreaData(name="sales", tables=list(tables.keys()), summary="")},
        tables=tables,
        edges=[],
        built_at=0.0,
        reflection_hash="hash",
    )


def test_query_engine_fallbacks_when_embedder_init_fails(monkeypatch: MonkeyPatch) -> None:
    """QueryEngine should continue with lexical retrieval if Embedder fails."""

    class _Boom:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """Always raise to simulate a backend failure."""
            msg = "simulated embedder failure"
            raise OSError(msg)

    # Force QueryEngine to hit the constructor path and fail
    monkeypatch.setattr(qe_mod, "Embedder", _Boom)

    card = _dummy_card()
    cfg = SchemaExplorerConfig(model_name="invalid:///path")

    engine = qe_mod.QueryEngine(card, cfg, embedder=None)

    # Embeddings are disabled but retrieval engine should be available
    assert engine.embedder is None
    assert engine.retrieval_engine is not None

    # Lexical retrieval should work and return a list (possibly empty)
    results = engine.retrieval_engine.retrieve_lexical("orders by month", k=5)
    assert isinstance(results, list)
