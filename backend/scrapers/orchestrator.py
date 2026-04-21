"""
scrapers/orchestrator.py
Coordinates all scrapers in priority order.

Priority (for unknown components not in local dataset):
  1. Datasheet scraper  (alldatasheet.com — primary spec source)
  2. Manufacturer scraper (TI / ON Semi — authoritative)
  3. Wikipedia scraper  (fallback — broad coverage)

Results are merged: earlier sources take priority, gaps filled by later ones.
All scrapers run safely — orchestrator never raises.
"""

import asyncio
from .base_scraper import ScraperResult
from .wikipedia_scraper import WikipediaScraper
from .datasheet_scraper import DatasheetScraper
from .manufacturer_scraper import ManufacturerScraper

# Instantiate once — scrapers are stateless
_wiki   = WikipediaScraper()
_ds     = DatasheetScraper()
_mfr    = ManufacturerScraper()


async def scrape_component(component_name: str) -> dict:
    """
    Public API — drop-in replacement for the old scraper.scrape_component().
    Returns the same shape: { specs: {type, voltage, current}, datasheet_url: str }

    Strategy:
      - Run datasheet + manufacturer scrapers concurrently (they're independent)
      - Run Wikipedia as fallback if both above are empty
      - Merge results: first non-empty value wins per field
    """
    print(f"[orchestrator] starting scrape for '{component_name}'")

    # Stage 1: run primary scrapers concurrently
    ds_result, mfr_result = await asyncio.gather(
        _safe_fetch(_ds,  component_name),
        _safe_fetch(_mfr, component_name),
    )

    # Merge: datasheet takes priority over manufacturer
    merged = ds_result.merge(mfr_result)

    # Stage 2: if still missing specs, try Wikipedia
    if not merged.success:
        print(f"[orchestrator] primary scrapers empty, falling back to Wikipedia")
        wiki_result = await _safe_fetch(_wiki, component_name)
        merged = merged.merge(wiki_result)

        # If Wikipedia found a datasheet link, prefer it over empty
        if not merged.datasheet_url and wiki_result.datasheet_url:
            merged.datasheet_url = wiki_result.datasheet_url

    # Stage 3: guaranteed datasheet URL fallback
    if not merged.datasheet_url:
        merged.datasheet_url = (
            f"https://www.alldatasheet.com/search/?q={component_name.replace(' ', '+')}"
        )

    print(f"[orchestrator] final → {merged}")

    # Return in original scraper.py shape for main.py compatibility
    return {
        "specs": merged.to_specs_dict(),
        "datasheet_url": merged.datasheet_url,
    }


async def _safe_fetch(scraper, name: str) -> ScraperResult:
    """Wrap any scraper call so it never propagates exceptions."""
    try:
        return await scraper.fetch_specs(name)
    except Exception as e:
        print(f"[orchestrator] {scraper.name} crashed unexpectedly: {e}")
        return ScraperResult(source=scraper.name, success=False, error=str(e))