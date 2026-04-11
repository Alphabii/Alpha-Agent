"""Platform scraper and applicator registry. Avoids circular imports."""

from __future__ import annotations

SCRAPERS: dict[str, type] = {}
APPLICATORS: dict[str, type] = {}


def register_scraper(name: str, cls: type):
    SCRAPERS[name] = cls


def register_applicator(name: str, cls: type):
    APPLICATORS[name] = cls
