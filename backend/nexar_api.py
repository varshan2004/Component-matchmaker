"""
nexar_api.py — Nexar GraphQL API client.
"""

import httpx
import time

TOKEN_URL   = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"

CLIENT_ID     = "6a07fd92-22dc-4e83-b02f-2643676096cd"
CLIENT_SECRET = "-HGVCqcz_pEmNpUYhM6XKOWW7-Rz5d50oBix"

_token_cache: dict = {"token": None, "expires_at": 0}

_VOLTAGE_KEYS = {
    "vsupply", "vcc", "vdd", "vout", "vin", "vds", "vce", "vceo",
    "supply_voltage", "operating_voltage", "output_voltage", "input_voltage",
    "voltage", "drain_voltage", "breakdown_voltage", "forward_voltage",
    "digital_supply", "analog_supply", "logic_voltage", "recommended_voltage"
}
_CURRENT_KEYS = {
    "iout", "id", "ic", "isupply", "icc", "idd",
    "output_current", "drain_current", "collector_current",
    "forward_current", "current", "max_current",
    "supply_current", "quiescent_current", "operating_current"
}
_TYPE_KEYS = {
    "type", "function", "device_type", "component_type",
    "transistor_type", "sensor_type", "category", "subcategory"
}


async def _get_token() -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(TOKEN_URL, data={
            "grant_type":    "client_credentials",
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        })
        r.raise_for_status()
        data = r.json()

    token      = data.get("access_token", "")
    expires_in = data.get("expires_in", 86400)
    _token_cache["token"]      = token
    _token_cache["expires_at"] = now + expires_in - 60
    return token


async def search_nexar(part_name: str) -> dict:
    """Search Nexar GraphQL. Returns normalized dict or {} on failure."""
    try:
        token = await _get_token()
    except Exception as e:
        print(f"[nexar] token failed: {e}")
        return {}

    query = {
        "query": f"""
        {{
          supSearch(q: "{part_name}", limit: 1) {{
            results {{
              part {{
                mpn
                manufacturer {{ name }}
                shortDescription
                bestDatasheet {{ url }}
                category {{ name }}
                specs {{
                  attribute {{ shortname name }}
                  displayValue
                }}
              }}
            }}
          }}
        }}
        """
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                GRAPHQL_URL,
                json=query,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type":  "application/json",
                }
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[nexar] request failed: {e}")
        return {}

    gql_data = data.get("data") or {}
    if not gql_data:
        print(f"[nexar] null data: {data.get('errors', [])}")
        return {}

    results = gql_data.get("supSearch", {}).get("results", [])
    if not results:
        print(f"[nexar] no results for '{part_name}'")
        return {}

    part = results[0].get("part")
    if not part:
        return {}

    specs_list = part.get("specs") or []
    if specs_list:
        print(f"[nexar] spec keys: {[s.get('attribute',{}).get('shortname') for s in specs_list[:8]]}")

    specs = _parse_specs(specs_list)

    # Use category as type fallback
    if not specs["type"]:
        cat = (part.get("category") or {}).get("name", "")
        if cat:
            specs["type"] = cat

    best_ds = part.get("bestDatasheet") or {}
    ds_url  = best_ds.get("url") or \
              f"https://www.alldatasheet.com/search/?q={part['mpn']}"

    print(f"[nexar] hit for '{part_name}' → {part['mpn']} specs={specs}")
    return {
        "name":          part["mpn"],
        "description":   part.get("shortDescription", ""),
        "manufacturer":  (part.get("manufacturer") or {}).get("name", ""),
        "specs":         specs,
        "datasheet_url": ds_url,
        "source":        "nexar",
    }


def _parse_specs(specs_list: list) -> dict:
    result = {"type": "", "voltage": "", "current": ""}
    for spec in specs_list:
        attr      = spec.get("attribute") or {}
        shortname = attr.get("shortname", "").lower()
        fullname  = attr.get("name", "").lower()
        value     = (spec.get("displayValue") or "").strip()
        if not value or value in {"-", "N/A"}:
            continue
        # Match on both shortname and full name
        for key in [shortname, fullname]:
            if not result["type"]    and any(k in key for k in _TYPE_KEYS):
                result["type"]    = value; break
            if not result["voltage"] and any(k in key for k in _VOLTAGE_KEYS):
                result["voltage"] = value; break
            if not result["current"] and any(k in key for k in _CURRENT_KEYS):
                result["current"] = value; break
    return result