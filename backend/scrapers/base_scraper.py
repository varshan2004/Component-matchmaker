"""
scrapers/base_scraper.py
Abstract base class for all scrapers.
Every scraper must implement fetch_specs(component_name) → ScraperResult.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ScraperResult:
    """
    Standardized result returned by every scraper.
    Partial results are allowed — empty string means not found.
    """
    source:       str   = ""          # e.g. "wikipedia", "alldatasheet", "manufacturer"
    voltage:      str   = ""
    current:      str   = ""
    comp_type:    str   = ""          # avoid shadowing Python built-in 'type'
    datasheet_url: str  = ""
    success:      bool  = False       # True only if at least one spec was extracted
    error:        str   = ""          # populated on failure, never raises

    def to_specs_dict(self) -> dict:
        """Convert to the shape expected by main.py."""
        return {
            "type":    self.comp_type,
            "voltage": self.voltage,
            "current": self.current,
        }

    def merge(self, other: "ScraperResult") -> "ScraperResult":
        """
        Fill gaps in self from other.
        self takes priority — only empty fields are overwritten.
        """
        return ScraperResult(
            source        = self.source,
            voltage       = self.voltage       or other.voltage,
            current       = self.current       or other.current,
            comp_type     = self.comp_type     or other.comp_type,
            datasheet_url = self.datasheet_url or other.datasheet_url,
            success       = self.success       or other.success,
        )


class BaseScraper(ABC):
    """All scrapers inherit from this. Enforces consistent interface."""

    name: str = "base"          # short identifier used in logs

    @abstractmethod
    async def fetch_specs(self, component_name: str) -> ScraperResult:
        """
        Fetch specs for the given component name.
        MUST NOT raise — catch all exceptions internally and return
        ScraperResult(success=False, error=str(e)).
        """
        ...

    def _empty(self, error: str = "") -> ScraperResult:
        """Convenience: return a failed result."""
        return ScraperResult(source=self.name, success=False, error=error)