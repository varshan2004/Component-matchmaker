"""
scraper.py — Wikipedia HTML infobox scraper (Phase 3 - improved key matching).
Never raises. Always returns partial data on failure.
"""

import httpx
from bs4 import BeautifulSoup
from normalizer import normalize_spec

HEADERS = {
    "User-Agent": "SmartComponentSystem/1.0 (educational project; contact@example.com)"
}

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


async def scrape_component(name: str) -> dict:
    """Scrape Wikipedia infobox for specs. Returns {specs, datasheet_url}."""
    url = f"https://en.wikipedia.org/wiki/{name.replace(' ', '_')}"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url, headers=HEADERS)
    except Exception as e:
        print(f"[scraper] network error for '{name}': {e}")
        return _empty()

    if r.status_code != 200:
        print(f"[scraper] HTTP {r.status_code} for '{name}'")
        return _empty()

    soup = BeautifulSoup(r.text, "html.parser")
    specs        = _parse_infobox(soup, name)
    datasheet_url = _find_datasheet(soup, name)

    print(f"[scraper] '{name}' → specs={specs}, ds={'yes' if datasheet_url else 'no'}")

    return {"specs": specs, "datasheet_url": datasheet_url}


def _parse_infobox(soup: BeautifulSoup, name: str) -> dict:
    specs   = {}
    infobox = soup.find("table", class_=lambda c: c and "infobox" in c)

    if not infobox:
        print(f"[scraper] no infobox found for '{name}'")
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

        if "type" not in specs and _matches(label, TYPE_KEYS):
            specs["type"] = normalize_spec(value, "type")

        elif "voltage" not in specs and _matches(label, VOLTAGE_KEYS):
            normalized = normalize_spec(value, "voltage")
            if normalized:
                specs["voltage"] = normalized

        elif "current" not in specs and _matches(label, CURRENT_KEYS):
            normalized = normalize_spec(value, "current")
            if normalized:
                specs["current"] = normalized

    return specs


def _find_datasheet(soup: BeautifulSoup, name: str) -> str:
    """Look in External Links section, fall back to alldatasheet.com search."""
    datasheet_kw = {"datasheet", "data sheet", "specification", "spec sheet"}

    ext = soup.find(id="External_links")
    if ext:
        ul = ext.find_next("ul")
        if ul:
            for a in ul.find_all("a", href=True):
                if any(kw in a.get_text(strip=True).lower() for kw in datasheet_kw):
                    href = a["href"]
                    if href.startswith("http"):
                        return href

    return f"https://www.alldatasheet.com/search/?q={name.replace(' ', '+')}"


def _matches(label: str, key_set: set) -> bool:
    return any(k in label for k in key_set)


def _empty() -> dict:
    return {"specs": {}, "datasheet_url": ""}