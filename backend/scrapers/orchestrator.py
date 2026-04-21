"""
scrapers/orchestrator.py
Coordinates scrapers in priority order.

Reality check on external sources:
  - alldatasheet.com  → 403 Forbidden (Cloudflare bot protection)
  - ti.com            → 403 Forbidden
  - onsemi.com        → 403 Forbidden

Only Wikipedia is reliably accessible without authentication.
The orchestrator now runs TWO Wikipedia passes (infobox + text regex),
which together extract significantly more data than either alone.

Priority:
  1. Wikipedia HTML infobox  (structured, most accurate)
  2. Wikipedia plain text    (regex, fills gaps from prose)
  3. Guaranteed datasheet URL fallback
"""

import asyncio
from .base_scraper import ScraperResult
from .wikipedia_scraper import WikipediaScraper

# Single instance — stateless scraper
_wiki = WikipediaScraper()


async def scrape_component(component_name: str) -> dict:
    """
    Public API — drop-in replacement for old scraper.scrape_component().
    Returns: { specs: {type, voltage, current}, datasheet_url: str }
    Never raises.
    """
    print(f"[orchestrator] scraping '{component_name}'")

    result = await _safe_fetch(_wiki, component_name)

    # Guaranteed datasheet URL — always give user something clickable
    if not result.datasheet_url:
        result.datasheet_url = (
            f"https://www.alldatasheet.com/search/?q={component_name.replace(' ', '+')}"
        )

    print(f"[orchestrator] result → "
          f"v={result.voltage} i={result.current} t={result.comp_type} "
          f"success={result.success}")

    return {
        "specs":         result.to_specs_dict(),
        "datasheet_url": result.datasheet_url,
    }


async def _safe_fetch(scraper, name: str) -> ScraperResult:
    """Wrap scraper call — never propagates exceptions."""
    try:
        return await scraper.fetch_specs(name)
    except Exception as e:
        print(f"[orchestrator] {scraper.name} crashed: {e}")
        return ScraperResult(source=scraper.name, success=False, error=str(e))