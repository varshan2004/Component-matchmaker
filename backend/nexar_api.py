"""
nexar_api.py — Nexar GraphQL API. Full spec extraction.
"""

import httpx, time

TOKEN_URL   = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"
CLIENT_ID     = "1e75f9e0-d714-460c-bca0-01ae1632b912"
CLIENT_SECRET = "wgsSXXI2MO6FmYzGm4nqWKMBzLQszk4DvUOa"

_token_cache: dict = {"token": None, "expires_at": 0}

# Nexar uses shortnames — map to our unified spec fields
NEXAR_SPEC_MAP = {
    "voltage":      {"vsupply","vcc","vdd","vout","vin","vds","vce","vceo",
                     "supply_voltage","operating_voltage","output_voltage",
                     "input_voltage","voltage","drain_voltage","forward_voltage",
                     "breakdown_voltage","vr","vrm"},
    "current":      {"iout","id","ic","isupply","icc","idd","output_current",
                     "drain_current","collector_current","forward_current",
                     "current","max_current","supply_current","if"},
    "power":        {"pd","power","power_dissipation","ptot","pmax"},
    "package":      {"case_package","package","case","housing","package_case"},
    "resistance":   {"rds","rds_on","rdson","ron","esr","resistance","r"},
    "capacitance":  {"capacitance","c","cap"},
    "inductance":   {"inductance","l","ind"},
    "frequency":    {"frequency","bandwidth","gbw","ft","switching_frequency",
                     "fsw","fmax","f3db"},
    "gain":         {"hfe","beta","gain","av","current_gain","dc_gain"},
    "temp_min":     {"tmin","temp_min","min_temp","operating_temp_min"},
    "temp_max":     {"tmax","temp_max","max_temp","operating_temp_max"},
    "rds_on":       {"rds_on","rdson","r_ds_on"},
    "vgs_th":       {"vgs_th","vgsth","gate_threshold","vth"},
    "dropout":      {"dropout","vdropout","headroom"},
    "accuracy":     {"accuracy","tolerance","initial_accuracy"},
    "logic_family": {"logic_family","technology","tech"},
    "mounting":     {"mounting","mounting_style"},
    "type":         {"type","function","device_type","component_type",
                     "transistor_type","category"},
}

DISPLAY_ORDER = [
    "type","voltage","current","power","resistance","capacitance",
    "inductance","frequency","gain","rds_on","vgs_th","dropout",
    "accuracy","logic_family","temp_range","package","mounting"
]


async def _get_token() -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(TOKEN_URL, data={
            "grant_type":"client_credentials",
            "client_id":CLIENT_ID,"client_secret":CLIENT_SECRET
        })
        r.raise_for_status()
        d = r.json()
    _token_cache["token"]      = d.get("access_token","")
    _token_cache["expires_at"] = now + d.get("expires_in",86400) - 60
    return _token_cache["token"]


async def search_nexar(part_name: str) -> dict:
    try:
        token = await _get_token()
    except Exception as e:
        print(f"[nexar] token failed: {e}")
        return {}

    query = {"query": f"""
    {{
      supSearch(q: "{part_name}", limit: 1) {{
        results {{
          part {{
            mpn
            manufacturer {{ name }}
            shortDescription
            bestDatasheet {{ url }}
            category {{ name }}
            specs {{ attribute {{ shortname name }} displayValue }}
            sellers(limit: 3) {{
              company {{ name }}
              offers {{
                prices {{ quantity price currency }}
                inventoryLevel
              }}
            }}
          }}
        }}
      }}
    }}
    """}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(GRAPHQL_URL, json=query, headers={
                "Authorization":f"Bearer {token}","Content-Type":"application/json"
            })
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[nexar] request failed: {e}")
        return {}

    gql = data.get("data") or {}
    if not gql:
        return {}

    results = gql.get("supSearch",{}).get("results",[])
    if not results:
        return {}

    part = results[0].get("part")
    if not part:
        return {}

    specs_list = part.get("specs") or []
    specs = _extract_all_specs(specs_list)

    # Category fallback
    if not specs.get("type"):
        cat = (part.get("category") or {}).get("name","")
        if cat:
            specs["type"] = cat

    pricing  = _parse_pricing(part.get("sellers",[]))
    best_ds  = part.get("bestDatasheet") or {}
    ds_url   = best_ds.get("url") or f"https://www.alldatasheet.com/search/?q={part['mpn']}"

    print(f"[nexar] '{part_name}' → {part['mpn']} | {len(specs)} spec fields")
    return {
        "name":          part["mpn"],
        "description":   part.get("shortDescription",""),
        "manufacturer":  (part.get("manufacturer") or {}).get("name",""),
        "specs":         specs,
        "pricing":       pricing,
        "datasheet_url": ds_url,
        "source":        "nexar",
    }


def _extract_all_specs(specs_list: list) -> dict:
    result = {}
    for spec in specs_list:
        attr      = spec.get("attribute") or {}
        shortname = attr.get("shortname","").lower()
        fullname  = attr.get("name","").lower()
        value     = (spec.get("displayValue") or "").strip()
        if not value or value.lower() in {"-","n/a","—"}:
            continue

        for field, keys in NEXAR_SPEC_MAP.items():
            if field not in result:
                if shortname in keys or fullname in keys or \
                   any(k in shortname for k in keys) or \
                   any(k in fullname  for k in keys):
                    result[field] = value
                    break

    # Temperature range
    if result.get("temp_min") or result.get("temp_max"):
        result["temp_range"] = f"{result.get('temp_min','')} to {result.get('temp_max','')}".strip(" to")

    return result


def _parse_pricing(sellers: list) -> dict:
    result = {"qty1":"","qty10":"","qty100":"","currency":"USD","seller":""}
    if not sellers:
        return result

    best_prices, best_seller = [], ""
    for seller in sellers:
        for offer in seller.get("offers",[]):
            prices = offer.get("prices",[])
            if len(prices) > len(best_prices):
                best_prices = prices
                best_seller = seller.get("company",{}).get("name","")

    result["seller"] = best_seller
    for pb in sorted(best_prices, key=lambda x: x.get("quantity",0)):
        qty = pb.get("quantity",0)
        try:
            ps = f"${float(pb.get('price',0)):.4f}"
        except:
            continue
        result["currency"] = pb.get("currency","USD")
        if qty <= 1   and not result["qty1"]:   result["qty1"]   = ps
        elif qty <= 10  and not result["qty10"]:  result["qty10"]  = ps
        elif qty <= 100 and not result["qty100"]: result["qty100"] = ps

    if not result["qty10"]  and result["qty1"]:  result["qty10"]  = result["qty1"]
    if not result["qty100"] and result["qty10"]: result["qty100"] = result["qty10"]
    return result