from __future__ import annotations

import re
from typing import Final

import pytest

from nl2sql_mcp.schema_tools.lightweight_ner import Entity, LightweightNER


def _has_entity(ents: list[Entity], *, label: str, canonical: str | None = None) -> bool:
    for e in ents:
        if e.label == label and (canonical is None or e.canonical == canonical):
            return True
    return False


@pytest.fixture(scope="module")
def ner() -> LightweightNER:
    return LightweightNER()


def test_country_canonical_alpha2_from_name(ner: LightweightNER) -> None:
    ents = ner.analyze("United States")
    assert _has_entity(ents, label="COUNTRY", canonical="US")


def test_country_canonical_alpha2_from_alpha3(ner: LightweightNER) -> None:
    ents = ner.analyze("USA")
    assert _has_entity(ents, label="COUNTRY", canonical="US")


def test_subdivision_canonical_iso_3166_2(ner: LightweightNER) -> None:
    # California should resolve to US-CA
    ents = ner.analyze("California")
    assert _has_entity(ents, label="SUBDIVISION", canonical="US-CA")


def test_currency_canonical_from_code(ner: LightweightNER) -> None:
    ents = ner.analyze("EUR amount")
    assert _has_entity(ents, label="CURRENCY", canonical="EUR")


def test_currency_canonical_from_name(ner: LightweightNER) -> None:
    ents = ner.analyze("euro revenue")
    assert _has_entity(ents, label="CURRENCY", canonical="EUR")


def test_timezone_detection_canonical(ner: LightweightNER) -> None:
    ents = ner.analyze("America/New_York")
    assert _has_entity(ents, label="TIMEZONE", canonical="America/New_York")


def test_extract_labels_uppercase(ner: LightweightNER) -> None:
    labels = ner.extract_labels("euro in United States, California, America/New_York")
    expected: Final[set[str]] = {"CURRENCY", "COUNTRY", "SUBDIVISION", "TIMEZONE"}
    assert expected.issubset(set(labels))

