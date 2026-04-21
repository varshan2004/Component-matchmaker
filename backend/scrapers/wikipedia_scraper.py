"""
scrapers/wikipedia_scraper.py — Enhanced Wikipedia scraper.

Two-stage extraction:
  Stage 1: HTML infobox parsing (structured — most accurate)
  Stage 2: Plain text regex extraction (from article body — catches what infobox misses)

Wikipedia is the only freely accessible source — we extract maximum value from it.
"""

import re
import httpx
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScraperResult
from normalizer import normalize_spec

HEADERS = {
    "User-Agent": "SmartComponentSystem/1.0 (educational project; contact@example.com)"
}

# ── Infobox label sets ────────────────────────────────────────────────────────

VOLTAGE_KEYS = {
    "voltage", "supply voltage", "operating voltage", "forward voltage",
    "output voltage", "input voltage", "vcc", "vdd", "drain voltage",
    "breakdown voltage", "collector-emitter voltage", "drain-source voltage",
    "vds", "vce", "vgs", "vceo", "bvdss", "output", "input", "supply",
    "working voltage", "reverse voltage", "peak voltage"
}
CURRENT_KEYS = {
    "current", "forward current", "max current", "output current",
    "operating current", "drain current", "collector current",
    "max. output current", "continuous drain current", "ic", "id",
    "output current", "peak current", "average current"
}
TYPE_KEYS = {
    "type", "electronic type", "component type", "device type",
    "transistor type", "working principle", "configuration", "polarity"
}

# ── Regex patterns for plain-text extraction ──────────────────────────────────

# Voltage: matches "60 V", "5V", "±15V", "4.5 to 16V", "1.25–37 V"
VOLTAGE_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:to|-|–)?\s*(?:\d+(?:\.\d+)?)?\s*'
    r'(?:kilo)?v(?:olt)?s?\b',
    re.IGNORECASE
)

# Current: matches "300 mA", "1A", "200mA", "1.5 ampere"
CURRENT_MA_RE = re.compile(r'(\d+(?:\.\d+)?)\s*m(?:illi)?a(?:mp(?:ere)?s?)?\b', re.IGNORECASE)
CURRENT_A_RE  = re.compile(r'(\d+(?:\.\d+)?)\s*a(?:mp(?:ere)?s?)?\b', re.IGNORECASE)

# Component type keywords found in article text
TYPE_PATTERNS = {
    "N-Channel MOSFET": [
        r'n.channel\s+mosfet', r'\bnmos\b', r'n.channel\s+fet',
        r'n.type\s+mosfet', r'n.channel\s+enhancement'
    ],
    "P-Channel MOSFET": [
        r'p.channel\s+mosfet', r'\bpmos\b', r'p.channel\s+fet',
        r'p.type\s+mosfet'
    ],
    "MOSFET":                     [r'\bmosfet\b', r'metal.oxide.semiconductor'],
    "NPN Transistor":             [r'\bnpn\b'],
    "PNP Transistor":             [r'\bpnp\b'],
    "Bipolar Junction Transistor":[r'\bbjt\b', r'bipolar junction'],
    "Positive Voltage Regulator": [r'positive.*voltage.*regulator'],
    "Negative Voltage Regulator": [r'negative.*voltage.*regulator'],
    "Adjustable Shunt Regulator": [r'shunt.*regulator', r'shunt.*voltage'],
    "Voltage Regulator":          [r'voltage\s+regulator', r'linear\s+regulator'],
    "Op-Amp":                     [r'operational\s+amplifier', r'\bop.amp\b'],
    "Timer IC":                   [r'timer\s+ic', r'555\s+timer'],
    "Rectifier Diode":            [r'rectifier\s+diode', r'power\s+diode'],
    "Signal Diode":               [r'signal\s+diode', r'switching\s+diode'],
    "Schottky Diode":             [r'schottky'],
    "Zener Diode":                [r'zener'],
    "Diode":                      [r'\bdiode\b'],
}

# Voltage context: only extract if preceded/followed by spec-related words
VOLTAGE_CONTEXT_RE = re.compile(
    r'(?:voltage|drain.source|collector.emitter|breakdown|supply|output|forward|reverse|vds|vce|bvdss)'
    r'.{0,30}?(\d+(?:\.\d+)?)\s*v(?:olt)?s?\b',
    re.IGNORECASE
)

CURRENT_CONTEXT_RE = re.compile(
    r'(?:current|drain|collector|output|forward|continuous|maximum|max)'
    r'.{0,30}?(\d+(?:\.\d+)?)\s*(m)?a(?:mp(?:ere)?s?)?\b',
    re.IGNORECASE
)


class WikipediaScraper(BaseScraper):
    name = "wikipedia"

    async def fetch_specs(self, component_name: str) -> ScraperResult:
        """
        Fetch both HTML (for infobox) and plain text (for regex extraction).
        Merge: infobox wins, text fills gaps.
        """
        html_result  = await self._scrape_html(component_name)
        text_result  = await self._scrape_text_api(component_name)

        # Infobox takes priority; text fills any gaps
        merged = html_result.merge(text_result)

        print(f"[wikipedia_scraper] '{component_name}' → "
              f"v={merged.voltage} i={merged.current} t={merged.comp_type} "
              f"ds={'yes' if merged.datasheet_url else 'no'}")

        return merged

    # ── Stage 1: HTML infobox ─────────────────────────────────────────────────

    async def _scrape_html(self, name: str) -> ScraperResult:
        url = f"https://en.wikipedia.org/wiki/{name.replace(' ', '_')}"
        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, headers=HEADERS
            ) as client:
                r = await client.get(url)
        except Exception as e:
            return self._empty(f"html request failed: {e}")

        if r.status_code != 200:
            return self._empty(f"HTML HTTP {r.status_code}")

        soup      = BeautifulSoup(r.text, "html.parser")
        specs     = self._parse_infobox(soup, name)
        ds_url    = self._find_datasheet_link(soup)
        has_specs = any(specs.values())

        return ScraperResult(
            source        = self.name,
            voltage       = specs.get("voltage", ""),
            current       = specs.get("current", ""),
            comp_type     = specs.get("type", ""),
            datasheet_url = ds_url,
            success       = has_specs,
        )

    def _parse_infobox(self, soup: BeautifulSoup, name: str) -> dict:
        specs   = {}
        infobox = soup.find("table", class_=lambda c: c and "infobox" in c)
        if not infobox:
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

            if "type"    not in specs and self._matches(label, TYPE_KEYS):
                specs["type"]    = normalize_spec(value, "type")
            if "voltage" not in specs and self._matches(label, VOLTAGE_KEYS):
                n = normalize_spec(value, "voltage")
                if n: specs["voltage"] = n
            if "current" not in specs and self._matches(label, CURRENT_KEYS):
                n = normalize_spec(value, "current")
                if n: specs["current"] = n

        return specs

    def _find_datasheet_link(self, soup: BeautifulSoup) -> str:
        kw  = {"datasheet", "data sheet", "specification", "spec sheet"}
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

    # ── Stage 2: Plain text regex extraction ──────────────────────────────────

    async def _scrape_text_api(self, name: str) -> ScraperResult:
        """
        Use Wikipedia Action API to get plain text, then extract specs with regex.
        This catches specs that appear in article prose but not in the infobox.
        """
        params = {
            "action":      "query",
            "format":      "json",
            "titles":      name,
            "prop":        "extracts",
            "explaintext": True,   # full plain text (not just intro)
            "redirects":   True,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
                r = await client.get("https://en.wikipedia.org/w/api.php", params=params)
        except Exception as e:
            return self._empty(f"text API failed: {e}")

        if r.status_code != 200:
            return self._empty(f"text API HTTP {r.status_code}")

        pages = r.json().get("query", {}).get("pages", {})
        if "-1" in pages:
            return self._empty("not found")

        page    = next(iter(pages.values()))
        text    = page.get("extract", "")
        if not text:
            return self._empty("empty extract")

        voltage   = self._extract_voltage(text)
        current   = self._extract_current(text)
        comp_type = self._extract_type(text)

        return ScraperResult(
            source    = f"{self.name}_text",
            voltage   = voltage,
            current   = current,
            comp_type = comp_type,
            success   = any([voltage, current, comp_type]),
        )

    def _extract_voltage(self, text: str) -> str:
        """Find voltage from article text using context-aware regex."""
        # Prefer context-aware match (near spec keywords)
        m = VOLTAGE_CONTEXT_RE.search(text)
        if m:
            return f"{m.group(1)}V"
        # Broader match: first voltage mention
        m = VOLTAGE_RE.search(text)
        if m:
            val = float(m.group(1))
            # Sanity check: component voltages are between 0.1V and 5000V
            if 0.1 <= val <= 5000:
                return f"{m.group(1)}V"
        return ""

    def _extract_current(self, text: str) -> str:
        """Find current from article text."""
        m = CURRENT_CONTEXT_RE.search(text)
        if m:
            val  = m.group(1)
            unit = "mA" if m.group(2) else "A"
            return f"{val}{unit}"
        # milliamps first
        m = CURRENT_MA_RE.search(text)
        if m:
            return f"{m.group(1)}mA"
        m = CURRENT_A_RE.search(text)
        if m:
            val = float(m.group(1))
            if 0.0001 <= val <= 1000:   # sanity check
                return f"{m.group(1)}A"
        return ""

    def _extract_type(self, text: str) -> str:
        """Identify component type from article text keywords."""
        text_lower = text.lower()
        for comp_type, patterns in TYPE_PATTERNS.items():
            if any(re.search(p, text_lower) for p in patterns):
                return comp_type
        return ""

    def _matches(self, label: str, key_set: set) -> bool:
        return any(k in label for k in key_set)