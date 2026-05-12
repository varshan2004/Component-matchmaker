"""
Smart Component Information System — Phase 4
Multi-distributor API integration.

Resolution flow for /component:
  1. SQLite cache          → instant return
  2. Local dataset         → curated specs + datasheet PDF
  3. Distributor APIs      → Mouser → Nexar → DigiKey (concurrent where possible)
  4. Wikipedia API         → description text
  5. Wikipedia scraper     → fallback specs if APIs returned nothing
  6. OpenRouter AI explain → plain-English description
  7. OpenRouter AI generate→ last resort if everything else failed
  8. Cache + return
"""

import json
import asyncio
import httpx
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import database
import alternatives as alt_engine
from scrapers.orchestrator import scrape_component
from scrapers.retry import with_retry
from openrouter_api import explain_component, generate_component, generate_alternatives
from mouser_api import search_mouser
from nexar_api  import search_nexar
from digikey_api import search_digikey

app = FastAPI(title="Smart Component Information System", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "SmartComponentSystem/1.0 (educational; contact@example.com)"}

_DATASET_PATH = Path(__file__).parent / "components_data.json"
with open(_DATASET_PATH) as f:
    COMPONENT_DATASET: dict = json.load(f)


@app.on_event("startup")
def on_startup():
    database.init_db()
    print(f"[startup] DB ready | dataset={len(COMPONENT_DATASET)} | APIs: Mouser+Nexar+DigiKey+OpenRouter")


# ── /component ────────────────────────────────────────────────────────────────

@app.get("/component")
async def get_component(name: str = Query(..., min_length=1)):

    # 1. Cache
    cached = database.get_cached(name)
    if cached:
        print(f"[component] cache hit: '{name}'")
        return cached

    # 2. Local dataset
    dataset_entry = _dataset_lookup(name)
    specs         = {}
    datasheet_url = ""
    description   = ""
    api_source    = None
    pricing       = {}

    if dataset_entry:
        print(f"[component] dataset hit: '{name}'")
        # Extract ALL available spec fields from dataset entry
        _SPEC_FIELDS = [
            "type","voltage","current","power","package","mounting",
            "resistance","capacitance","inductance","frequency","gain",
            "temp_range","temp_min","temp_max","rds_on","vgs_th",
            "dropout","accuracy","logic_family"
        ]
        specs = {k: dataset_entry.get(k,"") for k in _SPEC_FIELDS if dataset_entry.get(k)}
        datasheet_url = dataset_entry.get("datasheet_url", "")
        canonical     = dataset_entry["name"]

        # Fetch pricing — DigiKey first (most reliable), then Mouser + Nexar
        print(f"[component] fetching pricing for dataset part '{name}'")
        dk_res = await _safe_api(search_digikey, name)
        if dk_res and dk_res.get("pricing", {}).get("qty1"):
            pricing = dk_res["pricing"]
            print(f"[component] pricing from digikey: {pricing.get('qty1')}")
        else:
            m_res, n_res = await asyncio.gather(
                _safe_api(search_mouser, name),
                _safe_api(search_nexar,  name),
            )
            for api_res in [m_res, n_res]:
                if api_res and api_res.get("pricing", {}).get("qty1"):
                    pricing = api_res["pricing"]
                    print(f"[component] pricing from {api_res.get('source')}: {pricing.get('qty1')}")
                    break

    else:
        canonical = name

        # 3. Distributor APIs — DigiKey first (authoritative), then Mouser + Nexar
        print(f"[component] querying DigiKey first for '{name}'")
        api_data = await _safe_api(search_digikey, name)

        if not api_data or not any(api_data.get("specs", {}).values()):
            print(f"[component] DigiKey miss, trying Mouser + Nexar for '{name}'")
            mouser_result, nexar_result = await asyncio.gather(
                _safe_api(search_mouser, name),
                _safe_api(search_nexar,  name),
            )
            fallback = _pick_best([mouser_result, nexar_result])
            # Merge: use DigiKey data where available, fill gaps from Mouser/Nexar
            if fallback:
                api_data = fallback if not api_data else _merge_api(api_data, fallback)

        if api_data:
            api_source    = api_data.get("source", "api")
            api_specs     = api_data.get("specs", {})
            specs = {
                "type":    api_specs.get("type", ""),
                "voltage": api_specs.get("voltage", ""),
                "current": api_specs.get("current", ""),
            }
            pricing       = api_data.get("pricing", {})
            if not description:
                description = api_data.get("description", "")
            if not datasheet_url:
                datasheet_url = api_data.get("datasheet_url", "")
            canonical = api_data.get("name", name)

    # 4. Wikipedia description — best effort
    wiki_title = canonical
    try:
        wiki_name             = _simplify_name(canonical)
        wiki_desc, wiki_title = await _fetch_wikipedia_description(wiki_name)
        description           = wiki_desc   # Wikipedia preferred (richer)
        if not dataset_entry:
            canonical = wiki_title
        print(f"[component] Wikipedia hit for '{name}'")
    except HTTPException:
        print(f"[component] no Wikipedia page for '{name}'")

    # 5. Scrape specs if still empty (not in dataset, APIs returned nothing)
    if not dataset_entry and not any(specs.values()):
        print(f"[component] scraping specs for '{canonical}'")
        scraped       = await scrape_component(canonical)
        scraped_specs = scraped.get("specs", {})
        specs = {
            "type":    scraped_specs.get("type", ""),
            "voltage": scraped_specs.get("voltage", ""),
            "current": scraped_specs.get("current", ""),
        }
        if not datasheet_url:
            datasheet_url = scraped.get("datasheet_url", "")

    # 6+7. OpenRouter AI
    if description or any(specs.values()):
        # Have some data — AI explains it
        print(f"[component] generating AI explanation for '{canonical}'")
        ai_text = await explain_component(canonical, specs, description)
        final_description = ai_text if ai_text else description
        ai_generated = False
    else:
        # Nothing found anywhere — AI generates from knowledge
        print(f"[component] asking AI to generate data for '{canonical}'")
        ai_data = await generate_component(canonical)
        if not ai_data:
            raise HTTPException(
                status_code=404,
                detail=f"'{name}' not found. Try a more specific component name."
            )
        ai_generated      = True
        final_description = ai_data.get("description", "")
        ai_specs          = ai_data.get("specs", {})
        specs = {
            "type":    ai_specs.get("type", ""),
            "voltage": ai_specs.get("voltage", ""),
            "current": ai_specs.get("current", ""),
        }
        if not datasheet_url:
            datasheet_url = ai_data.get("datasheet_url", "")

    # Guaranteed datasheet fallback
    if not datasheet_url:
        datasheet_url = (
            f"https://www.alldatasheet.com/search/?q={canonical.replace(' ', '+')}"
        )

    # Determine source label
    if dataset_entry:
        source = "dataset"
    elif ai_generated:
        source = "ai"
    elif api_source:
        source = api_source
    else:
        source = "live"

    # 8. Build + cache
    result = {
        "name":          canonical,
        "description":   final_description,
        "specs":         specs,
        "datasheet_url": datasheet_url,
        "pricing":       pricing,
        "source":        source,
    }

    database.save_component(result)
    if name.upper() != canonical.upper():
        database.save_component({**result, "name": name})

    return result


# ── /alternatives ─────────────────────────────────────────────────────────────

@app.get("/alternatives")
async def get_alternatives(name: str = Query(..., min_length=1)):
    dataset_entry = _dataset_lookup(name)
    if dataset_entry:
        specs     = {k: dataset_entry.get(k, "") for k in ("type", "voltage", "current")}
        canonical = dataset_entry["name"]
    else:
        cached = database.get_cached(name)
        if cached:
            specs, canonical = cached.get("specs", {}), cached.get("name", name)
        else:
            try:
                comp      = await get_component(name)
                specs     = comp.get("specs", {})
                canonical = comp.get("name", name)
            except HTTPException:
                raise HTTPException(
                    status_code=404,
                    detail=f"Cannot find specs for '{name}' to suggest alternatives."
                )

    found = alt_engine.find_alternatives(canonical, specs, top_n=4)

    if not found:
        print(f"[alternatives] no dataset matches for '{canonical}', asking AI")
        found = await generate_alternatives(canonical, specs)

    # Enrich each alternative with its full dataset specs
    _SPEC_FIELDS = [
        "type","voltage","current","power","package","mounting",
        "resistance","capacitance","inductance","frequency","gain",
        "temp_range","rds_on","vgs_th","dropout","accuracy","logic_family"
    ]
    enriched = []
    for alt in found:
        alt_entry = _dataset_lookup(alt.get("name",""))
        if alt_entry:
            # Merge full dataset specs into the alternative
            full_specs = {k: alt_entry.get(k,"") for k in _SPEC_FIELDS if alt_entry.get(k)}
            alt = {**alt, "specs": full_specs,
                   "datasheet_url": alt_entry.get("datasheet_url","")}
        else:
            # Build specs dict from top-level fields for non-dataset alts
            alt_specs = {k: alt.get(k,"") for k in _SPEC_FIELDS if alt.get(k)}
            alt = {**alt, "specs": alt_specs}
        enriched.append(alt)

    return {"component": canonical, "specs": specs, "alternatives": enriched}



@app.get("/pricing")
async def get_pricing(name: str = Query(..., min_length=1)):
    """
    GET /pricing?name=BC547
    Returns live pricing from Mouser + Nexar.
    Used by frontend to fetch pricing for alternatives in parallel.
    """
    cached = database.get_cached(name)
    if cached and cached.get("pricing", {}).get("qty1"):
        return {"name": name, "pricing": cached["pricing"], "source": "cache"}

    dataset_entry = _dataset_lookup(name)
    lookup_name   = dataset_entry["name"] if dataset_entry else name

    # DigiKey first — most reliable pricing
    dk_res = await _safe_api(search_digikey, lookup_name)
    if dk_res and dk_res.get("pricing", {}).get("qty1"):
        print(f"[pricing] '{name}' → {dk_res['pricing'].get('qty1')} from digikey")
        return {"name": name, "pricing": dk_res["pricing"], "source": "digikey"}

    # Fallback: Mouser + Nexar concurrently
    mouser_res, nexar_res = await asyncio.gather(
        _safe_api(search_mouser, lookup_name),
        _safe_api(search_nexar,  lookup_name),
    )
    for res in [mouser_res, nexar_res]:
        if res and res.get("pricing", {}).get("qty1"):
            print(f"[pricing] '{name}' → {res['pricing'].get('qty1')} from {res.get('source')}")
            return {"name": name, "pricing": res["pricing"], "source": res.get("source")}

    return {"name": name, "pricing": {}, "source": "none"}

@app.get("/health")
async def health():
    from digikey_api import CLIENT_ID as dk_id
    return {
        "status":       "ok",
        "phase":        "4.0",
        "apis":         {
            "mouser":   "enabled",
            "nexar":    "enabled",
            "digikey":  "configured" if dk_id else "needs_setup",
            "openrouter": "enabled",
        },
        "dataset_size": len(COMPONENT_DATASET),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dataset_lookup(name: str) -> dict | None:
    key = name.strip().upper()
    for k, v in COMPONENT_DATASET.items():
        if k.upper() == key:
            return v
    return None


def _simplify_name(name: str) -> str:
    import re
    simplified = re.sub(r'[-/][A-Z]{1,4}$', '', name.strip())
    simplified = re.sub(r'[A-Z]\d[A-Z]\d?$', '', simplified)
    return simplified.strip('-') or name


async def _safe_api(fn, name: str) -> dict:
    """
    Call any async API function with one retry on network/timeout errors.
    Never raises — returns {} on final failure.
    """
    return await with_retry(fn, name, retries=1, delay=1.0) or {}


def _pick_best(results: list[dict]) -> dict:
    """Return the result with the most spec fields filled."""
    best = {}
    best_score = -1
    for r in results:
        if not r:
            continue
        score = sum(1 for v in r.get("specs", {}).values() if v)
        if score > best_score:
            best_score = score
            best = r
    return best


async def _fetch_wikipedia_description(name: str) -> tuple[str, str]:
    params = {
        "action": "query", "format": "json",
        "titles": name, "prop": "extracts",
        "exintro": True, "explaintext": True, "redirects": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(WIKIPEDIA_API, params=params, headers=HEADERS)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Wikipedia timed out.")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Wikipedia {r.status_code}.")

    pages = r.json().get("query", {}).get("pages", {})
    if "-1" in pages:
        raise HTTPException(status_code=404, detail=f"'{name}' not found on Wikipedia.")

    page    = next(iter(pages.values()))
    extract = page.get("extract", "").strip()
    if not extract:
        raise HTTPException(status_code=404, detail=f"No description for '{name}'.")

    sentences  = [s.strip() for s in extract.split(".") if s.strip()]
    short_desc = ". ".join(sentences[:3]) + "."
    return short_desc, page.get("title", name)