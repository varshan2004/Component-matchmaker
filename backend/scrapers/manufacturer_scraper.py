"""
scrapers/manufacturer_scraper.py
Scrapes Texas Instruments and ON Semiconductor product pages.
These are the two most common sources for the components in our dataset.

TI:      https://www.ti.com/product/{name}
ON Semi: https://www.onsemi.com/search#q={name}

Both return structured HTML with spec tables.
Never raises — always returns partial result.
"""

import httpx
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScraperResult
from normalizer import normalize_spec

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 12.0


class ManufacturerScraper(BaseScraper):
    name = "manufacturer"

    async def fetch_specs(self, component_name: str) -> ScraperResult:
        """
        Try TI first, then ON Semi.
        Return first successful result.
        """
        # Try Texas Instruments
        ti_result = await self._scrape_ti(component_name)
        if ti_result.success:
            print(f"[manufacturer_scraper] TI hit for '{component_name}'")
            return ti_result

        # Try ON Semiconductor
        on_result = await self._scrape_onsemi(component_name)
        if on_result.success:
            print(f"[manufacturer_scraper] ON Semi hit for '{component_name}'")
            return on_result

        print(f"[manufacturer_scraper] no result for '{component_name}'")
        return self._empty("no manufacturer page found")

    # ── Texas Instruments ────────────────────────────────────────────────────

    async def _scrape_ti(self, name: str) -> ScraperResult:
        url = f"https://www.ti.com/product/{name.upper()}"
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, follow_redirects=True, headers=HEADERS
            ) as client:
                r = await client.get(url)
        except Exception as e:
            return self._empty(f"TI request failed: {e}")

        # TI returns 200 with "product not found" content OR redirects to search
        if r.status_code != 200:
            return self._empty(f"TI HTTP {r.status_code}")

        # If redirected away from /product/ path, product doesn't exist on TI
        if "/product/" not in str(r.url):
            return self._empty("not a TI product page")

        soup      = BeautifulSoup(r.text, "html.parser")
        voltage   = ""
        current   = ""
        comp_type = ""
        ds_url    = ""

        # TI product pages have a spec table with data-attribute rows
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True).lower()
            value = cells[1].get_text(" ", strip=True)

            if not value or value == "-":
                continue

            if not comp_type and "type" in label:
                comp_type = normalize_spec(value, "type")
            elif not voltage and any(k in label for k in {"voltage", "vcc", "supply"}):
                n = normalize_spec(value, "voltage")
                if n:
                    voltage = n
            elif not current and "current" in label:
                n = normalize_spec(value, "current")
                if n:
                    current = n

        # TI datasheet links: look for PDF link on page
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".pdf") and "ti.com" in href:
                ds_url = href
                break

        success = any([voltage, current, comp_type])
        return ScraperResult(
            source=self.name, voltage=voltage, current=current,
            comp_type=comp_type, datasheet_url=ds_url, success=success
        )

    # ── ON Semiconductor ─────────────────────────────────────────────────────

    async def _scrape_onsemi(self, name: str) -> ScraperResult:
        # ON Semi product pages follow /products/{name} pattern
        url = f"https://www.onsemi.com/products/{name.upper()}"
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, follow_redirects=True, headers=HEADERS
            ) as client:
                r = await client.get(url)
        except Exception as e:
            return self._empty(f"ON Semi request failed: {e}")

        if r.status_code != 200:
            return self._empty(f"ON Semi HTTP {r.status_code}")

        soup      = BeautifulSoup(r.text, "html.parser")
        voltage   = ""
        current   = ""
        comp_type = ""
        ds_url    = ""

        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True).lower()
            value = cells[1].get_text(" ", strip=True)

            if not value or value == "-":
                continue

            if not comp_type and "type" in label:
                comp_type = normalize_spec(value, "type")
            elif not voltage and any(k in label for k in {"voltage", "vcc"}):
                n = normalize_spec(value, "voltage")
                if n:
                    voltage = n
            elif not current and "current" in label:
                n = normalize_spec(value, "current")
                if n:
                    current = n

        # ON Semi PDF links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".pdf"):
                ds_url = href if href.startswith("http") \
                         else f"https://www.onsemi.com{href}"
                break

        success = any([voltage, current, comp_type])
        return ScraperResult(
            source=self.name, voltage=voltage, current=current,
            comp_type=comp_type, datasheet_url=ds_url, success=success
        )