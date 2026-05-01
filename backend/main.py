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

    if dataset_entry:
        print(f"[component] dataset hit: '{name}'")
        specs = {
            "type":    dataset_entry.get("type", ""),
            "voltage": dataset_entry.get("voltage", ""),
            "current": dataset_entry.get("current", ""),
        }
        datasheet_url = dataset_entry.get("datasheet_url", "")
        canonical     = dataset_entry["name"]

    else:
        canonical = name

        # 3. Distributor APIs — run Mouser + Nexar concurrently, DigiKey as fallback
        print(f"[component] querying distributor APIs for '{name}'")
        mouser_result, nexar_result = await asyncio.gather(
            _safe_api(search_mouser, name),
            _safe_api(search_nexar,  name),
        )

        # Pick best result: prefer Mouser (more detailed specs), then Nexar
        api_data = _pick_best([mouser_result, nexar_result])

        # If neither had specs, try DigiKey
        if not api_data or not any(api_data.get("specs", {}).values()):
            print(f"[component] Mouser+Nexar empty, trying DigiKey for '{name}'")
            api_data = await _safe_api(search_digikey, name) or api_data

        if api_data:
            api_source    = api_data.get("source", "api")
            api_specs     = api_data.get("specs", {})
            specs = {
                "type":    api_specs.get("type", ""),
                "voltage": api_specs.get("voltage", ""),
                "current": api_specs.get("current", ""),
            }
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

    return {"component": canonical, "specs": specs, "alternatives": found}


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
    """Call any async API function safely — never raises."""
    try:
        return await fn(name) or {}
    except Exception as e:
        print(f"[component] API error ({fn.__name__}): {e}")
        return {}


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