"""
scrapers/wikipedia_scraper.py
Scrapes Wikipedia HTML infobox for component specs.
Migrated from the original scraper.py — same logic, new interface.
"""

import httpx
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScraperResult
from normalizer import normalize_spec

HEADERS = {
    "User-Agent": "SmartComponentSystem/1.0 (educational project; contact@example.com)"
}

# Infobox row label → spec field mapping
VOLTAGE_KEYS = {
    "voltage", "supply voltage", "operating voltage", "forward voltage",
    "output voltage", "input voltage", "vcc", "vdd", "drain voltage",
    "breakdown voltage", "collector-emitter voltage", "drain-source voltage",
    "output", "input", "supply"
}
CURRENT_KEYS = {
    "current", "forward current", "max current", "output current",
    "operating current", "drain current", "collector current",
    "max. output current", "continuous drain current", "ic"
}
TYPE_KEYS = {
    "type", "electronic type", "component type", "device type",
    "transistor type", "working principle", "configuration"
}


class WikipediaScraper(BaseScraper):
    name = "wikipedia"

    async def fetch_specs(self, component_name: str) -> ScraperResult:
        url = f"https://en.wikipedia.org/wiki/{component_name.replace(' ', '_')}"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                r = await client.get(url, headers=HEADERS)
        except httpx.TimeoutException:
            return self._empty(f"timeout fetching '{component_name}'")
        except Exception as e:
            return self._empty(f"network error: {e}")

        if r.status_code != 200:
            return self._empty(f"HTTP {r.status_code}")

        soup    = BeautifulSoup(r.text, "html.parser")
        specs   = self._parse_infobox(soup, component_name)
        ds_url  = self._find_datasheet(soup, component_name)

        has_specs = any([specs.get("type"), specs.get("voltage"), specs.get("current")])
        print(f"[wikipedia_scraper] '{component_name}' → specs={specs}")

        return ScraperResult(
            source        = self.name,
            voltage       = specs.get("voltage", ""),
            current       = specs.get("current", ""),
            comp_type     = specs.get("type", ""),
            datasheet_url = ds_url,
            success       = has_specs,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _parse_infobox(self, soup: BeautifulSoup, name: str) -> dict:
        specs   = {}
        infobox = soup.find("table", class_=lambda c: c and "infobox" in c)
        if not infobox:
            print(f"[wikipedia_scraper] no infobox for '{name}'")
            return specs

        for row in infobox.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not (th and td):
                continue
            label = th.get_text(" ", strip=True).lower().strip()
            value = td.get_text(" ", strip=True).strip()
            if not value or value in {"-", "—", "N/A", "n/a"}:
                continue

            if "type" not in specs and self._matches(label, TYPE_KEYS):
                specs["type"] = normalize_spec(value, "type")
            elif "voltage" not in specs and self._matches(label, VOLTAGE_KEYS):
                n = normalize_spec(value, "voltage")
                if n:
                    specs["voltage"] = n
            elif "current" not in specs and self._matches(label, CURRENT_KEYS):
                n = normalize_spec(value, "current")
                if n:
                    specs["current"] = n

        return specs

    def _find_datasheet(self, soup: BeautifulSoup, name: str) -> str:
        kw = {"datasheet", "data sheet", "specification", "spec sheet"}
        ext = soup.find(id="External_links")
        if ext:
            ul = ext.find_next("ul")
            if ul:
                for a in ul.find_all("a", href=True):
                    if any(k in a.get_text(strip=True).lower() for k in kw):
                        href = a["href"]
                        if href.startswith("http"):
                            return href
        return ""

    def _matches(self, label: str, key_set: set) -> bool:
        return any(k in label for k in key_set)