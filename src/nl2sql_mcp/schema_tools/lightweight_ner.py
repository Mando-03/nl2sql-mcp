"""Lightweight NER implementation using regex patterns and gazetteers.

This module provides a fast, lightweight alternative to spaCy for Named Entity Recognition
specifically optimized for database column names. It uses pattern matching and gazetteer
lookups to identify semantic entities (person, org, gpe, loc) in column identifiers.

Classes:
- LightweightNER: Main NER class using regex + gazetteer approach
- MockDoc: spaCy-compatible interface for seamless integration
- MockEntity: spaCy-compatible entity interface
"""

from __future__ import annotations

import re
from typing import Any

from fastmcp.utilities.logging import get_logger

# Logger
_logger = get_logger("lightweight_ner")


class LightweightNER:
    """Lightweight NER optimized for database column names.

    Uses regex patterns and gazetteer lookups to identify semantic entities
    in column names. Optimized for speed and minimal memory footprint.
    """

    def __init__(self) -> None:
        """Initialize the lightweight NER with gazetteers and patterns."""
        self.gazetteers = self._build_gazetteers()
        self.patterns = self._compile_patterns()

    def _build_gazetteers(self) -> dict[str, set[str]]:
        """Build lightweight gazetteers for fast entity lookup."""
        return {
            "person": {
                # Common person-related terms in column names
                "first",
                "firstname",
                "fname",
                "forename",
                "given",
                "givenname",
                "last",
                "lastname",
                "lname",
                "surname",
                "family",
                "familyname",
                "full",
                "fullname",
                "name",
                "displayname",
                "username",
                "customer_name",
                "user_name",
                "employee_name",
                "person_name",
                "contact_name",
                "client_name",
                "member_name",
                "owner_name",
                "author_name",
                "creator_name",
                "manager_name",
                "supervisor_name",
                # Common first/last names that appear in column names
                "john",
                "jane",
                "smith",
                "johnson",
                "williams",
                "brown",
                "jones",
                "garcia",
                "miller",
                "davis",
                "rodriguez",
                "martinez",
                "anderson",
                "taylor",
                "thomas",
                "hernandez",
                "moore",
                "martin",
                "jackson",
                "thompson",
                "white",
                "lopez",
                "lee",
                "gonzalez",
                # Title indicators
                "mr",
                "mrs",
                "ms",
                "dr",
                "prof",
                "professor",
            },
            "org": {
                # Organization indicators
                "company",
                "corp",
                "corporation",
                "inc",
                "incorporated",
                "ltd",
                "limited",
                "llc",
                "co",
                "group",
                "enterprises",
                "organization",
                "org",
                "business",
                "firm",
                "agency",
                "department",
                "dept",
                "division",
                "unit",
                "team",
                "branch",
                "vendor",
                "supplier",
                "client",
                "partner",
                "contractor",
                "manufacturer",
                "distributor",
                "retailer",
                "wholesaler",
                # Company name patterns
                "company_name",
                "org_name",
                "business_name",
                "vendor_name",
                "supplier_name",
                "client_name",
                "partner_name",
                "firm_name",
                "agency_name",
                "department_name",
                "division_name",
                # Common company suffixes
                "plc",
                "sa",
                "gmbh",
            },
            "gpe": {  # Geopolitical entities
                "country",
                "nation",
                "state",
                "province",
                "region",
                "territory",
                "district",
                "county",
                "city",
                "town",
                "municipality",
                "locale",
                "area",
                "zone",
                "sector",
                "nationality",
                "citizenship",
                # Country codes (ISO 3166)
                "usa",
                "us",
                "uk",
                "gb",
                "can",
                "ca",
                "aus",
                "au",
                "deu",
                "de",
                "fra",
                "fr",
                "jpn",
                "jp",
                "chn",
                "cn",
                "ind",
                "in",
                "bra",
                "br",
                "rus",
                "ru",
                "esp",
                "es",
                # Common countries/regions
                "america",
                "canada",
                "england",
                "germany",
                "france",
                "spain",
                "italy",
                "japan",
                "china",
                "india",
                "brazil",
                "russia",
                "australia",
                "mexico",
                "argentina",
                "netherlands",
                "sweden",
                # US states (abbreviated)
                "california",
                "texas",
                "florida",
                "newyork",
                "illinois",
                "pennsylvania",
                "ohio",
                "georgia",
                "northcarolina",
                "michigan",
            },
            "loc": {  # Physical locations
                "address",
                "location",
                "place",
                "position",
                "site",
                "venue",
                "facility",
                "building",
                "office",
                "headquarters",
                "branch",
                "store",
                "warehouse",
                "plant",
                "campus",
                "floor",
                "room",
                "suite",
                "apartment",
                "unit",
                # Address components
                "street",
                "road",
                "avenue",
                "boulevard",
                "lane",
                "drive",
                "way",
                "court",
                "circle",
                "plaza",
                "square",
                "zip",
                "zipcode",
                "postal",
                "postcode",
                "mailcode",
                "coordinates",
                "latitude",
                "longitude",
                "lat",
                "lng",
                # Location types
                "home",
                "work",
                "shipping",
                "billing",
                "mailing",
            },
        }

    def _compile_patterns(self) -> dict[str, list[re.Pattern[str]]]:
        """Compile regex patterns for entity detection."""
        return {
            "person": [
                # Name column patterns
                re.compile(r"\b(?:first|last|full|given|family)_?names?\b", re.IGNORECASE),
                re.compile(
                    r"\b(?:customer|user|employee|contact|person|client|member|owner)_?names?\b",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"\b(?:author|creator|manager|supervisor|admin)_?names?\b", re.IGNORECASE
                ),
                re.compile(r"\bnames?\b", re.IGNORECASE),
                # Name format patterns (for actual names in data)
                re.compile(r"\b[A-Z][a-z]+(?:[_\s][A-Z][a-z]+)+\b"),
                re.compile(r"\b(?:mr|mrs|ms|dr|prof)\.?\s*[a-z_]+\b", re.IGNORECASE),
                # ID patterns that suggest person
                re.compile(r"\b(?:user|customer|employee|person|contact)_?ids?\b", re.IGNORECASE),
            ],
            "org": [
                # Organization patterns
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
                re.compile(
                    r"\b(?:manufacturer|distributor|retailer|wholesaler)_?names?\b", re.IGNORECASE
                ),
                # ID patterns that suggest organization
                re.compile(
                    r"\b(?:company|vendor|supplier|client|partner|org)_?ids?\b", re.IGNORECASE
                ),
            ],
            "gpe": [
                # Geopolitical patterns
                re.compile(
                    r"\b(?:country|state|province|region|territory)_?(?:names?|codes?)?\b",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"\b(?:city|town|municipality|county|district)_?names?\b", re.IGNORECASE
                ),
                re.compile(r"\b[A-Z]{2,3}\b"),  # Country/state codes
                re.compile(r"\bnationality\b", re.IGNORECASE),
                re.compile(r"\bcitizenship\b", re.IGNORECASE),
                # Location with political context
                re.compile(r"\b(?:birth|origin)_?(?:country|state|city)\b", re.IGNORECASE),
            ],
            "loc": [
                # Location patterns
                re.compile(
                    r"\b(?:address|location|place|position|site)_?(?:names?)?\b", re.IGNORECASE
                ),
                re.compile(
                    r"\b(?:street|road|avenue|blvd|lane|drive|way)_?(?:names?)?\b", re.IGNORECASE
                ),
                re.compile(r"\b(?:zip|postal)_?codes?\b", re.IGNORECASE),
                re.compile(
                    r"\b(?:building|office|facility|warehouse|store)_?(?:names?)?\b", re.IGNORECASE
                ),
                re.compile(r"\b(?:coordinates|latitude|longitude|lat|lng)\b", re.IGNORECASE),
                re.compile(
                    r"\b(?:home|work|shipping|billing|mailing)_?(?:address|location)\b",
                    re.IGNORECASE,
                ),
            ],
        }

    def extract_entities(self, column_name: str) -> list[str]:
        """Extract entities from column name using lightweight approach.

        Args:
            column_name: Database column name to analyze

        Returns:
            List of detected entity types (person, org, gpe, loc)
        """
        if not column_name:
            return []

        entities: set[str] = set()
        name_clean = column_name.lower().strip()
        name_normalized = re.sub(r"[^a-z0-9_]", "_", name_clean)

        # 1. Fast gazetteer lookup (O(1) per term)
        words = set(name_normalized.replace("_", " ").split())
        words.update(name_normalized.split("_"))
        words.add(name_normalized)  # Check full normalized name

        for entity_type, gazetteer in self.gazetteers.items():
            if any(term in gazetteer for term in words if term):
                entities.add(entity_type)

        # 2. Pattern matching for unmatched cases (only if no gazetteer matches)
        if not entities:
            for entity_type, patterns in self.patterns.items():
                for pattern in patterns:
                    if pattern.search(name_clean) or pattern.search(column_name):
                        entities.add(entity_type)
                        break  # One match per type is enough

        return list(entities)

    def batch_extract_entities(self, column_names: list[str]) -> dict[str, list[str]]:
        """Efficiently extract entities from multiple column names.

        Args:
            column_names: List of column names to process

        Returns:
            Dictionary mapping column names to their detected entities
        """
        return {name: self.extract_entities(name) for name in column_names}


class MockEntity:
    """Mock spaCy entity interface for backward compatibility."""

    def __init__(self, label: str) -> None:
        """Initialize mock entity with label.

        Args:
            label: Entity label (person, org, gpe, loc)
        """
        # Convert to spaCy-style uppercase format
        label_mapping = {"person": "PERSON", "org": "ORG", "gpe": "GPE", "loc": "LOC"}
        self.label_ = label_mapping.get(label.lower(), label.upper())


class MockDoc:
    """Mock spaCy doc interface for backward compatibility."""

    def __init__(self, entities: list[MockEntity]) -> None:
        """Initialize mock doc with entities.

        Args:
            entities: List of detected entities
        """
        self.ents = entities


class SpaCyCompatibleNER:
    """spaCy-compatible wrapper for LightweightNER.

    Provides the same interface as spaCy's NLP pipeline for seamless
    drop-in replacement in existing code.
    """

    def __init__(self) -> None:
        """Initialize the spaCy-compatible NER wrapper."""
        self.ner = LightweightNER()

    def __call__(self, text: str) -> MockDoc:
        """Process text and return mock spaCy doc interface.

        Args:
            text: Text to process (column name)

        Returns:
            MockDoc with detected entities
        """
        try:
            entity_labels = self.ner.extract_entities(text)
            mock_entities = [MockEntity(label) for label in entity_labels]
            return MockDoc(mock_entities)
        except (AttributeError, ValueError, TypeError) as e:
            _logger.debug("Lightweight NER failed for text '%s': %s", text, e)
            return MockDoc([])


# Global instance for compatibility
_lightweight_ner = SpaCyCompatibleNER()


def get_lightweight_ner() -> SpaCyCompatibleNER:
    """Get the global lightweight NER instance.

    Returns:
        SpaCy-compatible NER instance
    """
    return _lightweight_ner


# Performance testing function
def benchmark_extraction(column_names: list[str], iterations: int = 1000) -> dict[str, Any]:
    """Benchmark the extraction performance.

    Args:
        column_names: List of column names to test
        iterations: Number of iterations to run

    Returns:
        Performance metrics dictionary
    """
    import time  # noqa: PLC0415

    ner = LightweightNER()

    # Single extraction benchmark
    start_time = time.perf_counter()
    for _ in range(iterations):
        for name in column_names:
            ner.extract_entities(name)
    end_time = time.perf_counter()

    total_extractions = len(column_names) * iterations
    total_time = end_time - start_time
    avg_time_ms = (total_time / total_extractions) * 1000

    # Batch extraction benchmark
    start_time = time.perf_counter()
    for _ in range(iterations):
        ner.batch_extract_entities(column_names)
    batch_end_time = time.perf_counter()

    batch_time = batch_end_time - start_time
    batch_avg_ms = (batch_time / iterations) * 1000

    return {
        "total_extractions": total_extractions,
        "total_time_seconds": total_time,
        "avg_time_per_extraction_ms": avg_time_ms,
        "batch_avg_time_ms": batch_avg_ms,
        "extractions_per_second": total_extractions / total_time,
    }


if __name__ == "__main__":
    # Example usage and testing
    ner = LightweightNER()

    test_columns = [
        "customer_name",
        "employee_id",
        "company_address",
        "country_code",
        "user_email",
        "vendor_name",
        "billing_address",
        "first_name",
        "organization_id",
        "city_name",
        "John_Smith",
        "Microsoft_Corp",
        "California",
        "street_address",
        "postal_code",
        "phone_number",
    ]

    print("Lightweight NER Test Results:")  # noqa: T201
    print("-" * 40)  # noqa: T201
    for column in test_columns:
        entities = ner.extract_entities(column)
        print(f"{column:20} -> {entities}")  # noqa: T201

    # Performance benchmark
    print("\nPerformance Benchmark:")  # noqa: T201
    print("-" * 40)  # noqa: T201
    results = benchmark_extraction(test_columns, 100)
    print(f"Average extraction time: {results['avg_time_per_extraction_ms']:.3f}ms")  # noqa: T201
    print(f"Extractions per second: {results['extractions_per_second']:.0f}")  # noqa: T201
