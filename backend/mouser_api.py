"""
mouser_api.py — Mouser Electronics Search API client.
"""

import httpx

API_KEY  = "c6ecc768-a102-457e-8b9d-4f0c17103327"
BASE_URL = "https://api.mouser.com/api/v1"

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
}

# Broad matching — covers sensors, MCUs, ICs, passives, power
_VOLTAGE_KEYS = {
    "voltage", "supply voltage", "operating voltage", "output voltage",
    "input voltage", "vcc", "vdd", "vds", "vce", "breakdown voltage",
    "supply voltage range", "operating supply voltage", "digital supply",
    "analog supply", "power supply", "logic voltage", "interface voltage",
    "recommended operating voltage", "max voltage", "min voltage"
}
_CURRENT_KEYS = {
    "current", "output current", "drain current", "collector current",
    "forward current", "continuous drain current", "max current",
    "supply current", "operating current", "quiescent current",
    "standby current", "sleep current", "active current", "icc", "idd"
}
_TYPE_KEYS = {
    "type", "device type", "component type", "transistor type",
    "function", "product type", "sensor type", "ic type",
    "output type", "product category", "category", "subcategory",
    "configuration", "technology", "architecture"
}


async def search_mouser(part_name: str) -> dict:
    """Search Mouser. Returns normalized dict or {} on failure."""
    payload = {
        "SearchByKeywordRequest": {
            "keyword":           part_name,
            "records":           1,
            "startingRecord":    0,
            "searchOptions":     "string",
            "searchWithSYMlink": "string"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{BASE_URL}/search/keyword?apiKey={API_KEY}",
                json=payload,
                headers=HEADERS
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[mouser] request failed: {e}")
        return {}

    errors = data.get("Errors", [])
    if errors:
        print(f"[mouser] API errors: {errors}")
        return {}

    parts = data.get("SearchResults", {}).get("Parts", [])
    if not parts:
        print(f"[mouser] no results for '{part_name}'")
        return {}

    part = parts[0]
    mpn  = part.get("ManufacturerPartNumber", part_name)
    print(f"[mouser] hit for '{part_name}' → {mpn}")

    # Debug: print all attributes so we can see what Mouser returns
    attrs = part.get("ProductAttributes", [])
    if attrs:
        print(f"[mouser] attributes: {[(a.get('AttributeName'), a.get('AttributeValue')) for a in attrs[:8]]}")

    specs  = _parse_specs(attrs)
    ds_url = part.get("DataSheetUrl", "") or \
             f"https://www.alldatasheet.com/search/?q={part_name.replace(' ', '+')}"

    # Use category as type fallback if spec parsing got nothing
    if not specs["type"]:
        cat = part.get("Category", "") or part.get("ProductDescription", "")
        if cat:
            specs["type"] = cat.split("|")[0].strip()[:60]

    return {
        "name":          mpn,
        "description":   part.get("Description", ""),
        "manufacturer":  part.get("Manufacturer", ""),
        "specs":         specs,
        "datasheet_url": ds_url,
        "source":        "mouser",
    }


def _parse_specs(attributes: list) -> dict:
    result = {"type": "", "voltage": "", "current": ""}
    for attr in attributes:
        name  = attr.get("AttributeName", "").lower().strip()
        value = attr.get("AttributeValue", "").strip()
        if not value or value in {"-", "N/A", "~", ""}:
            continue
        if not result["type"]    and any(k in name for k in _TYPE_KEYS):
            result["type"]    = value
        if not result["voltage"] and any(k in name for k in _VOLTAGE_KEYS):
            result["voltage"] = value
        if not result["current"] and any(k in name for k in _CURRENT_KEYS):
            result["current"] = value
    return result