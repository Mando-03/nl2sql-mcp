"""Authoritative, list-free NER for column names using ISO/CLDR sources.

This module uses  authoritative, standards backed sources:

- Countries/Subdivisions: ISO-3166 via ``pycountry``
- Currencies: ISO-4217 codes, names, and symbols via ``Babel`` (CLDR)
- Time zones: IANA TZ database via ``zoneinfo`` (with ``tzdata`` when needed)

The recognizer is optimized for database column identifiers, focusing on
high-precision detection of geopolitical/currency/timezone mentions and
common name/organization/location patterns in identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal
import unicodedata
from zoneinfo import available_timezones

from babel.numbers import (  # type: ignore[reportMissingTypeStubs]
    get_currency_name,
    get_currency_symbol,
    list_currencies,
)
from fastmcp.utilities.logging import get_logger
import pycountry  # type: ignore[reportMissingTypeStubs]

# Logger
_logger = get_logger("lightweight_ner")


Label = Literal[
    "PERSON",
    "ORG",
    "GPE",
    "LOC",
    "COUNTRY",
    "SUBDIVISION",
    "CURRENCY",
    "TIMEZONE",
]


@dataclass(slots=True)
class Entity:
    """Recognized entity with canonical normalization.

    Attributes:
        label: Entity type label
        text: Matched surface text (normalized for multi-token where needed)
        span: Start/end character offsets in the normalized identifier string
        canonical: Canonical code or identifier (e.g., ISO3166 alpha-2)
        score: Confidence score (0.0..1.0)
        source: Origin of the signal ("canonical" from gazetteers, "pattern" from regex)
    """

    label: Label
    text: str
    span: tuple[int, int]
    canonical: str | None
    score: float
    source: Literal["canonical", "pattern"]


def _normalize(s: str) -> str:
    """Normalize a string for identifier matching.

    - Lowercase, remove diacritics, replace non-alnum with single underscore,
      and collapse consecutive underscores.
    """
    s_nfkd = unicodedata.normalize("NFKD", s)
    s_ascii = "".join(ch for ch in s_nfkd if not unicodedata.combining(ch))
    s_lower = s_ascii.lower()
    s_sub = re.sub(r"[^a-z0-9]+", "_", s_lower)
    return re.sub(r"_+", "_", s_sub).strip("_")


class LightweightNER:
    """Lightweight, standards-backed NER for database identifiers.

    Builds gazetteers from ISO/CLDR sources at initialization and uses
    regex patterns for common PERSON/ORG/GPE/LOC hints in column names.
    """

    def __init__(self, *, locale: str = "en") -> None:
        """Initialize with authoritative gazetteers and compiled patterns.

        Args:
            locale: CLDR locale code for currency names/symbols (default: "en").
        """
        self.locale = locale
        self._gazetteers = self._build_gazetteers()
        self._patterns = self._compile_patterns()

    def _build_gazetteers(self) -> dict[Label, dict[str, str]]:
        """Build authoritative gazetteers mapping term -> canonical code.

        Returns:
            Mapping from label to term dictionary (term -> canonical value).
        """
        gaz: dict[Label, dict[str, str]] = {
            "COUNTRY": {},
            "SUBDIVISION": {},
            "CURRENCY": {},
            "TIMEZONE": {},
            # Pattern-only labels do not need gazetteers
            "PERSON": {},
            "ORG": {},
            "GPE": {},
            "LOC": {},
        }

        # Country terms from ISO-3166
        for country in pycountry.countries:  # type: ignore[assignment]
            alpha2 = getattr(country, "alpha_2", None)
            if not isinstance(alpha2, str):
                continue

            names: list[str] = [
                str(getattr(country, attr))
                for attr in ("name", "official_name", "common_name")
                if hasattr(country, attr)
            ]
            # Include alpha-2 and alpha-3 codes as names
            codes = [
                str(getattr(country, a)) for a in ("alpha_2", "alpha_3") if hasattr(country, a)
            ]
            names.extend(codes)

            for n in names:
                term = _normalize(n)
                if term:
                    gaz["COUNTRY"][term] = alpha2

        # Subdivision terms from ISO-3166-2
        for subdiv in pycountry.subdivisions:  # type: ignore[attr-defined]
            code = getattr(subdiv, "code", None)
            if not code:
                continue
            term = _normalize(getattr(subdiv, "name", code))
            if term:
                gaz["SUBDIVISION"][term] = code
            # Also add code itself normalized (e.g., US-CA)
            gaz["SUBDIVISION"][_normalize(code)] = code

        # Currencies (ISO-4217 via Babel)
        for code in list_currencies(locale=self.locale):
            code_str = str(code)
            gaz["CURRENCY"][_normalize(code_str)] = code_str
            # Name and symbol (if available)
            name = get_currency_name(code_str, locale=self.locale)
            term_name = _normalize(name)
            if term_name:
                gaz["CURRENCY"][term_name] = code_str
            sym = get_currency_symbol(code_str, locale=self.locale)
            # Symbols are non-alnum; store as-is in a separate key form
            # We'll detect them via regex rather than gazetteer tokens.
            if sym and sym in {"$", "€", "£", "¥", "₩", "₹", "₽", "₺", "₫", "₦"}:
                gaz["CURRENCY"][sym] = code_str

        # Time zones (IANA TZ IDs)
        for tz in sorted(available_timezones()):
            gaz["TIMEZONE"][_normalize(tz)] = tz

        return gaz

    def _compile_patterns(self) -> dict[Label, list[re.Pattern[str]]]:
        """Compile regex patterns for PERSON/ORG/GPE/LOC and money symbols."""
        patterns: dict[Label, list[re.Pattern[str]]] = {
            "PERSON": [
                re.compile(r"\b(?:first|last|full|given|family)_?names?\b", re.IGNORECASE),
                re.compile(
                    r"\b(?:customer|user|employee|contact|person|client|member|owner)_?names?\b",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"\b(?:author|creator|manager|supervisor|admin)_?names?\b", re.IGNORECASE
                ),
                re.compile(r"\b(?:mr|mrs|ms|dr|prof)\.?[_\s]?[a-z]+\b", re.IGNORECASE),
                re.compile(r"\b(?:user|customer|employee|person|contact)_?ids?\b", re.IGNORECASE),
            ],
            "ORG": [
                re.compile(
                    r"\b(?:company|corp|corporation|organization|business)_?names?\b",
                    re.IGNORECASE,
                ),
                re.compile(r"\b\w+_?(?:inc|corp|llc|ltd|co|plc)\b", re.IGNORECASE),
                re.compile(
                    r"\b(?:vendor|supplier|client|partner|contractor)_?names?\b", re.IGNORECASE
                ),
                re.compile(
                    r"\b(?:dept|department|division|unit|agency|firm)_?names?\b", re.IGNORECASE
                ),
            ],
            "GPE": [
                re.compile(
                    r"\b(?:country|state|province|region|territory)_?(?:names?|codes?)?\b",
                    re.IGNORECASE,
                ),
                re.compile(r"\b(?:nationality|citizenship)\b", re.IGNORECASE),
            ],
            "LOC": [
                re.compile(r"\b(?:address|location|place|position|site)\b", re.IGNORECASE),
                re.compile(r"\b(?:street|road|avenue|blvd|lane|drive|way)\b", re.IGNORECASE),
                re.compile(r"\b(?:zip|postal)_?codes?\b", re.IGNORECASE),
                re.compile(r"\b(?:coordinates|latitude|longitude|lat|lng)\b", re.IGNORECASE),
                re.compile(
                    r"\b(?:home|work|shipping|billing|mailing)_?(?:address|location)\b",
                    re.IGNORECASE,
                ),
            ],
            # Money symbol patterns (to supplement CURRENCY gazetteer)
            "CURRENCY": [
                re.compile(r"[€£¥₹₩₽₺₫₦]"),
                re.compile(r"\$"),
            ],
        }
        return patterns

    def analyze(self, text: str) -> list[Entity]:  # noqa: PLR0912
        """Analyze text and return recognized entities with canonical forms.

        Args:
            text: Column name or identifier to analyze.

        Returns:
            List of recognized entities.
        """
        if not text:
            return []

        norm = _normalize(text)
        if not norm:
            return []

        # Candidate tokens: unigrams + joined bigrams/trigrams for multi-word names
        raw_tokens = [t for t in re.split(r"[^a-z0-9]+", norm) if t]
        candidates: list[str] = []
        candidates.extend(raw_tokens)
        candidates.extend(
            "_".join(raw_tokens[i : i + n])
            for n in (2, 3)
            for i in range(len(raw_tokens) - n + 1)
        )
        # Also include the full normalized identifier
        candidates.append(norm)

        results: list[Entity] = []

        # Gazetteer lookups
        for label, terms in self._gazetteers.items():
            if not terms:
                continue
            for cand in candidates:
                canon = terms.get(cand)
                if canon:
                    start = norm.find(cand)
                    end = start + len(cand) if start >= 0 else (0 + len(cand))
                    results.append(
                        Entity(
                            label=label,
                            text=cand,
                            span=(max(0, start), max(0, end)),
                            canonical=canon,
                            score=0.9,
                            source="canonical",
                        )
                    )

        # Pattern-based currency symbols
        for pat in self._patterns.get("CURRENCY", []):
            m = pat.search(text)
            if m:
                results.append(
                    Entity(
                        label="CURRENCY",
                        text=m.group(0),
                        span=(m.start(), m.end()),
                        canonical=None,
                        score=0.6,
                        source="pattern",
                    )
                )

        # Pattern-based PERSON/ORG/GPE/LOC
        for label in ("PERSON", "ORG", "GPE", "LOC"):
            for pat in self._patterns.get(label, []):
                m = pat.search(text)
                if m:
                    results.append(
                        Entity(
                            label=label,
                            text=m.group(0),
                            span=(m.start(), m.end()),
                            canonical=None,
                            score=0.6,
                            source="pattern",
                        )
                    )

        # De-duplicate by (label, canonical or text)
        seen: set[tuple[str, str]] = set()
        deduped: list[Entity] = []
        for ent in results:
            key = (ent.label, ent.canonical or ent.text)
            if key not in seen:
                seen.add(key)
                deduped.append(ent)

        return deduped

    def extract_labels(self, text: str) -> list[str]:
        """Return unique labels present in the text (uppercase)."""
        return list({ent.label for ent in self.analyze(text)})

    def batch_analyze(self, texts: list[str]) -> dict[str, list[Entity]]:
        """Analyze a batch of texts.

        Returns a mapping from input to list of entities.
        """
        return {t: self.analyze(t) for t in texts}


def benchmark_extraction(column_names: list[str], iterations: int = 1000) -> dict[str, Any]:
    """Benchmark the extraction performance for the new analyzer."""
    import time  # noqa: PLC0415

    ner = LightweightNER()

    start_time = time.perf_counter()
    for _ in range(iterations):
        for name in column_names:
            _ = ner.analyze(name)
    end_time = time.perf_counter()

    total_extractions = len(column_names) * iterations
    total_time = end_time - start_time
    avg_time_ms = (total_time / total_extractions) * 1000 if total_extractions else 0.0

    return {
        "total_extractions": total_extractions,
        "total_time_seconds": total_time,
        "avg_time_per_extraction_ms": avg_time_ms,
        "extractions_per_second": (total_extractions / total_time) if total_time else 0.0,
    }


if __name__ == "__main__":
    ner = LightweightNER()
    tests = [
        "customer_name",
        "company_address",
        "country_code",
        "region_name",
        "state_province",
        "currency_code",
        "billing_address",
        "first_name",
        "organization_id",
        "city_name",
        "California",
        "US",
        "EUR_amount",
        "America/New_York",
    ]
    for t in tests:
        print(t, "->", [f"{e.label}:{e.canonical or e.text}" for e in ner.analyze(t)])  # noqa: T201
