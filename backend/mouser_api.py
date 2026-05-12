"""
mouser_api.py — Mouser Electronics Search API.
Full spec extraction: all meaningful attributes, not just voltage/current.
"""

import httpx

API_KEY  = "c6ecc768-a102-457e-8b9d-4f0c17103327"
BASE_URL = "https://api.mouser.com/api/v1"
HEADERS  = {"Content-Type": "application/json", "Accept": "application/json"}

# ── Attribute → Spec Field Mapping ────────────────────────────────────────────
# Each entry: set of substrings to match against AttributeName (lowercase)

SPEC_MAP = {
    "voltage": {
        "voltage", "supply voltage", "operating voltage", "output voltage",
        "input voltage", "vcc", "vdd", "vds", "vce", "breakdown voltage",
        "supply voltage range", "operating supply voltage", "power supply",
        "logic voltage", "forward voltage", "collector-emitter voltage",
        "drain-source voltage", "working voltage", "rated voltage"
    },
    "current": {
        "current", "output current", "drain current", "collector current",
        "forward current", "continuous drain current", "max current",
        "supply current", "operating current", "quiescent current",
        "standby current", "continuous collector current", "ic(max)"
    },
    "power": {
        "power dissipation", "power rating", "maximum power", "pd",
        "max power", "total power", "power consumption"
    },
    "package": {
        "package type", "package", "case", "housing", "case style",
        "outline", "mounting type"  # not included — separate field
    },
    "mounting": {
        "mounting", "mount", "mounting style", "surface mount",
        "through hole", "assembly"
    },
    "resistance": {
        "resistance", "ohm", "esr", "on-resistance", "rds", "rce"
    },
    "capacitance": {
        "capacitance", "farad", "pf", "nf", "uf", "μf"
    },
    "inductance": {
        "inductance", "henry", "uh", "mh", "μh"
    },
    "frequency": {
        "frequency", "bandwidth", "switching frequency", "self-resonant",
        "unity gain bandwidth", "gbw", "gain bandwidth", "ft", "transition"
    },
    "gain": {
        "gain", "hfe", "dc current gain", "current gain", "beta",
        "voltage gain", "open loop gain"
    },
    "temp_min": {
        "minimum operating temperature", "min temp", "temp min",
        "min operating temp", "lower temperature"
    },
    "temp_max": {
        "maximum operating temperature", "max temp", "temp max",
        "max operating temp", "upper temperature"
    },
    "rds_on": {
        "rds(on)", "drain-source on-resistance", "on-state resistance",
        "on resistance", "rdson"
    },
    "vgs_th": {
        "gate threshold", "vgs(th)", "threshold voltage", "vgs threshold"
    },
    "type": {
        "type", "device type", "component type", "transistor type",
        "function", "product type", "sensor type", "ic type",
        "configuration", "technology"
    },
    "logic_family": {
        "logic family", "logic type", "technology family"
    },
    "dropout": {
        "dropout voltage", "dropout", "headroom"
    },
    "accuracy": {
        "accuracy", "tolerance", "initial accuracy", "output accuracy",
        "reference accuracy", "regulation"
    },
}

# Which spec fields to keep (ordered for display)
DISPLAY_ORDER = [
    "type", "voltage", "current", "power", "resistance", "capacitance",
    "inductance", "frequency", "gain", "rds_on", "vgs_th", "dropout",
    "accuracy", "logic_family", "temp_min", "temp_max", "package", "mounting"
]

SKIP_VALUES = {"-", "N/A", "~", "", "n/a", "—", "na"}


async def search_mouser(part_name: str) -> dict:
    payload = {
        "SearchByKeywordRequest": {
            "keyword": part_name, "records": 1,
            "startingRecord": 0, "searchOptions": "string",
            "searchWithSYMlink": "string"
        }
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{BASE_URL}/search/keyword?apiKey={API_KEY}",
                json=payload, headers=HEADERS
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[mouser] request failed: {e}")
        return {}

    if data.get("Errors"):
        return {}

    parts = data.get("SearchResults", {}).get("Parts", [])
    if not parts:
        return {}

    part  = parts[0]
    mpn   = part.get("ManufacturerPartNumber", part_name)
    attrs = part.get("ProductAttributes", [])

    print(f"[mouser] '{part_name}' → {mpn} | {len(attrs)} attributes")

    specs = _extract_all_specs(attrs)

    # Category fallback for type
    if not specs.get("type"):
        cat = part.get("Category", "") or part.get("ProductDescription", "")
        if cat:
            specs["type"] = cat.split("|")[0].strip()[:60]

    pricing  = _parse_pricing(part.get("PriceBreaks", []))
    ds_url   = part.get("DataSheetUrl", "") or \
               f"https://www.alldatasheet.com/search/?q={part_name.replace(' ', '+')}"

    return {
        "name":          mpn,
        "description":   part.get("Description", ""),
        "manufacturer":  part.get("Manufacturer", ""),
        "specs":         specs,
        "pricing":       pricing,
        "stock":         part.get("Availability", ""),
        "datasheet_url": ds_url,
        "source":        "mouser",
    }


async def _fetch_by_part_number(client_ref, part_name: str) -> list:
    """Try Mouser's exact part number search for richer attribute data."""
    payload = {
        "SearchByPartNumberRequest": {
            "mouserPartNumber": part_name,
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{BASE_URL}/search/partnumber?apiKey={API_KEY}",
                json=payload, headers=HEADERS
            )
            r.raise_for_status()
            data = r.json()
        parts = data.get("SearchResults", {}).get("Parts", [])
        if parts:
            return parts[0].get("ProductAttributes", [])
    except Exception as e:
        print(f"[mouser] exact search failed: {e}")
    return []


def _extract_all_specs(attributes: list) -> dict:
    """Extract all meaningful specs from Mouser ProductAttributes."""
    result = {k: "" for k in SPEC_MAP}

    for attr in attributes:
        raw_name = attr.get("AttributeName", "")
        name     = raw_name.lower().strip()
        value    = attr.get("AttributeValue", "").strip()

        if not value or value.lower() in SKIP_VALUES:
            continue

        for field, keywords in SPEC_MAP.items():
            if not result[field] and any(k in name for k in keywords):
                result[field] = value
                break   # don't double-assign same attribute

    # Build temperature range from min/max
    if result.get("temp_min") or result.get("temp_max"):
        t_min = result.get("temp_min", "").replace("C","°C").strip()
        t_max = result.get("temp_max", "").replace("C","°C").strip()
        result["temp_range"] = f"{t_min} to {t_max}".strip(" to")
    else:
        result["temp_range"] = ""

    return {k: v for k, v in result.items() if v}  # drop empty fields


def _parse_pricing(price_breaks: list) -> dict:
    result = {"qty1": "", "qty10": "", "qty100": "", "currency": "USD"}
    if not price_breaks:
        return result

    for pb in price_breaks:
        qty   = pb.get("Quantity", 0)
        price = str(pb.get("Price", "")).replace("$", "").replace(",", "").strip()
        result["currency"] = pb.get("Currency", "USD")
        try:
            ps = f"${float(price):.4f}"
        except ValueError:
            ps = price

        if qty <= 1   and not result["qty1"]:   result["qty1"]   = ps
        elif qty <= 10  and not result["qty10"]:  result["qty10"]  = ps
        elif qty <= 100 and not result["qty100"]: result["qty100"] = ps

    if not result["qty10"]  and result["qty1"]:  result["qty10"]  = result["qty1"]
    if not result["qty100"] and result["qty10"]: result["qty100"] = result["qty10"]
    return result


# Ordered list for consistent frontend display
def ordered_specs(specs: dict) -> list[tuple[str, str]]:
    """Return specs as ordered (label, value) pairs for display."""
    LABELS = {
        "type": "Type", "voltage": "Voltage", "current": "Current",
        "power": "Power Diss.", "resistance": "Resistance",
        "capacitance": "Capacitance", "inductance": "Inductance",
        "frequency": "Frequency", "gain": "Gain / hFE",
        "rds_on": "RDS(on)", "vgs_th": "VGS(th)",
        "dropout": "Dropout V", "accuracy": "Accuracy",
        "logic_family": "Logic Family",
        "temp_range": "Temp Range", "package": "Package",
        "mounting": "Mounting",
    }
    result = []
    for key in DISPLAY_ORDER + ["temp_range"]:
        if key in specs and specs[key]:
            result.append((LABELS.get(key, key.title()), specs[key]))
    return result