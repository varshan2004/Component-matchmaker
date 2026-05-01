"""
digikey_api.py — DigiKey Product Search API v4 client.
OAuth2 client credentials flow.

To get your Client ID + Secret:
  1. Go to https://developer.digikey.com
  2. Login: sangamesh.mannapur@qwalton.com / Sushanth@1432
  3. Create an app → copy Client ID and Client Secret
  4. Paste below

API Docs: https://developer.digikey.com/products/product-information/productsearch
"""

import httpx
import time

# ── Fill these after getting from developer.digikey.com ───────────────────────
CLIENT_ID     = "IWGrhpWqRGFzBrGPx8CzSOW6UWo3areAoanNl13I15FPcU50"   # paste your DigiKey client ID here
CLIENT_SECRET = "KAyXIWyLHHg28OpVHvGiBCS6LxGGvDM3Suhxezu3uPDAur1JjAM9igdETEbEFtaG"   # paste your DigiKey client secret here
# ─────────────────────────────────────────────────────────────────────────────

TOKEN_URL  = "https://api.digikey.com/v1/oauth2/token"
SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"

_token_cache: dict = {"token": None, "expires_at": 0}

_VOLTAGE_KEYS = {
    "voltage", "supply voltage", "operating voltage", "output voltage",
    "input voltage", "vcc", "vdd", "vds", "breakdown voltage"
}
_CURRENT_KEYS = {
    "current", "output current", "drain current", "collector current",
    "forward current", "max current"
}
_TYPE_KEYS = {"type", "device type", "component type", "transistor type"}


async def _get_token() -> str:
    """Fetch DigiKey OAuth2 token, reuse if still valid."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("DigiKey CLIENT_ID and CLIENT_SECRET not configured.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(TOKEN_URL, data={
            "grant_type":    "client_credentials",
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        })
        r.raise_for_status()
        data = r.json()

    token      = data.get("access_token", "")
    expires_in = data.get("expires_in", 1800)
    _token_cache["token"]      = token
    _token_cache["expires_at"] = now + expires_in - 60
    return token


async def search_digikey(part_name: str) -> dict:
    """
    Search DigiKey for a component by part number.
    Returns normalized dict or {} on failure.
    Never raises.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[digikey] not configured — skipping")
        return {}

    try:
        token = await _get_token()
    except Exception as e:
        print(f"[digikey] token failed: {e}")
        return {}

    headers = {
        "Authorization":  f"Bearer {token}",
        "X-DIGIKEY-Client-Id": CLIENT_ID,
        "Content-Type":   "application/json",
        "Accept":         "application/json",
    }

    payload = {
        "Keywords":      part_name,
        "RecordCount":   1,
        "RecordStartPos": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(SEARCH_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[digikey] request failed: {e}")
        return {}

    products = data.get("Products", [])
    if not products:
        print(f"[digikey] no results for '{part_name}'")
        return {}

    product = products[0]
    print(f"[digikey] hit for '{part_name}' → {product.get('ManufacturerProductNumber')}")

    specs  = _parse_specs(product.get("Parameters", []))
    ds_url = ""
    for doc in product.get("DatasheetUrl", ""):
        if doc:
            ds_url = doc
            break
    if not ds_url:
        ds_url = product.get("DatasheetUrl", "") or \
                 f"https://www.alldatasheet.com/search/?q={part_name.replace(' ', '+')}"

    return {
        "name":          product.get("ManufacturerProductNumber", part_name),
        "description":   product.get("ProductDescription", ""),
        "manufacturer":  product.get("Manufacturer", {}).get("Name", ""),
        "specs":         specs,
        "datasheet_url": ds_url,
        "source":        "digikey",
    }


def _parse_specs(parameters: list) -> dict:
    """
    Parse DigiKey Parameters list into {type, voltage, current}.
    DigiKey returns: [{ "ParameterText": "Voltage", "ValueText": "5V" }]
    """
    result = {"type": "", "voltage": "", "current": ""}
    for param in parameters:
        name  = param.get("ParameterText", "").lower().strip()
        value = param.get("ValueText", "").strip()
        if not value or value in {"-", "N/A"}:
            continue
        if not result["type"]    and any(k in name for k in _TYPE_KEYS):
            result["type"]    = value
        if not result["voltage"] and any(k in name for k in _VOLTAGE_KEYS):
            result["voltage"] = value
        if not result["current"] and any(k in name for k in _CURRENT_KEYS):
            result["current"] = value
    return result