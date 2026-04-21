"""
scrapers/datasheet_scraper.py
Scrapes alldatasheet.com for component specs.
Target: search results page → first result detail page → spec table.
Always returns partial data — never raises.
"""

import re
import httpx
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScraperResult
from normalizer import normalize_spec

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SEARCH_URL  = "https://www.alldatasheet.com/search/?q={query}"
TIMEOUT     = 12.0


class DatasheetScraper(BaseScraper):
    name = "alldatasheet"

    async def fetch_specs(self, component_name: str) -> ScraperResult:
        """
        Flow:
          1. Search alldatasheet.com for component_name
          2. Extract first result's detail-page URL
          3. Scrape spec table from detail page
        """
        try:
            detail_url = await self._get_detail_url(component_name)
            if not detail_url:
                print(f"[datasheet_scraper] no search result for '{component_name}'")
                return self._empty("no search result found")

            result = await self._scrape_detail(detail_url, component_name)
            return result

        except Exception as e:
            print(f"[datasheet_scraper] unexpected error for '{component_name}': {e}")
            return self._empty(str(e))

    # ── Step 1: Search page ──────────────────────────────────────────────────

    async def _get_detail_url(self, name: str) -> str | None:
        """Search alldatasheet and return the first result URL."""
        url = SEARCH_URL.format(query=name.replace(" ", "+"))

        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, follow_redirects=True, headers=HEADERS
            ) as client:
                r = await client.get(url)
        except Exception as e:
            print(f"[datasheet_scraper] search request failed: {e}")
            return None

        if r.status_code != 200:
            print(f"[datasheet_scraper] search HTTP {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # alldatasheet search results: links in <a> tags with href containing /view.jsp
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Detail pages follow pattern: /datasheet/...html or view.jsp
            if "datasheet-pdf" in href or "view.jsp" in href:
                if href.startswith("http"):
                    return href
                return f"https://www.alldatasheet.com{href}"

        # Fallback: check if redirected directly to a datasheet page
        if "datasheet-pdf" in str(r.url) or "view.jsp" in str(r.url):
            return str(r.url)

        return None

    # ── Step 2: Detail page ──────────────────────────────────────────────────

    async def _scrape_detail(self, url: str, name: str) -> ScraperResult:
        """Scrape spec table from alldatasheet detail page."""
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, follow_redirects=True, headers=HEADERS
            ) as client:
                r = await client.get(url)
        except Exception as e:
            return self._empty(f"detail page request failed: {e}")

        if r.status_code != 200:
            return self._empty(f"detail page HTTP {r.status_code}")

        soup = BeautifulSoup(r.text, "html.parser")

        voltage   = ""
        current   = ""
        comp_type = ""

        # alldatasheet uses <tr> rows with spec label + value
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label = cells[0].get_text(" ", strip=True).lower()
            value = cells[1].get_text(" ", strip=True)

            if not value or value in {"-", "N/A", "—"}:
                continue

            if not comp_type and any(k in label for k in
                    {"type", "function", "application", "description"}):
                comp_type = normalize_spec(value, "type")

            elif not voltage and any(k in label for k in
                    {"voltage", "vcc", "vdd", "supply", "output v", "input v"}):
                n = normalize_spec(value, "voltage")
                if n:
                    voltage = n

            elif not current and any(k in label for k in
                    {"current", "output current", "drain current"}):
                n = normalize_spec(value, "current")
                if n:
                    current = n

        # Also try to find the part description at the top of the page
        if not comp_type:
            comp_type = self._extract_page_type(soup)

        success = any([voltage, current, comp_type])
        print(f"[datasheet_scraper] '{name}' → v={voltage} i={current} t={comp_type}")

        return ScraperResult(
            source        = self.name,
            voltage       = voltage,
            current       = current,
            comp_type     = comp_type,
            datasheet_url = url,    # detail page IS the datasheet page
            success       = success,
        )

    def _extract_page_type(self, soup: BeautifulSoup) -> str:
        """Try to extract component type from page title or description."""
        # alldatasheet puts description in <span> near top
        for tag in soup.find_all(["h1", "h2", "span", "b"]):
            text = tag.get_text(strip=True)
            if 10 < len(text) < 80:
                lower = text.lower()
                if any(kw in lower for kw in
                       {"transistor", "regulator", "amplifier", "diode",
                        "mosfet", "timer", "oscillator", "comparator"}):
                    return normalize_spec(text, "type")
        return ""