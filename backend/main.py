"""
Smart Component Information System — Phase 3.3
Resolution flow for /component:
  1. SQLite cache        → return immediately (AI description already stored)
  2. Local dataset       → exact specs + real datasheet PDF
  3. Wikipedia API       → description text (context for AI)
  4. Wikipedia scraper   → specs for unknown parts
  5a. OpenRouter explain → if we have specs/description from above sources
  5b. OpenRouter generate→ if EVERYTHING failed — AI generates specs from knowledge
  6. Save to cache → return
"""

import json
import httpx
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import database
import alternatives as alt_engine
from scrapers.orchestrator import scrape_component
from openrouter_api import explain_component, generate_component, generate_alternatives

app = FastAPI(title="Smart Component Information System", version="3.3.0")

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
    print(f"[startup] DB ready | dataset={len(COMPONENT_DATASET)} | openrouter=enabled")


# ── /component ────────────────────────────────────────────────────────────────

@app.get("/component")
async def get_component(name: str = Query(..., min_length=1)):

    # 1. Cache — AI description already stored, return immediately
    cached = database.get_cached(name)
    if cached:
        print(f"[component] cache hit: '{name}'")
        return cached

    # 2. Local dataset
    dataset_entry = _dataset_lookup(name)
    specs         = {}
    datasheet_url = ""
    description   = ""

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

    # 3. Wikipedia description — best effort, never fatal
    try:
        wiki_name             = _simplify_name(canonical)
        wiki_desc, wiki_title = await _fetch_wikipedia_description(wiki_name)
        description           = wiki_desc
        # Only update canonical for unknown components — prevents BC547→BC548 rename
        if not dataset_entry:
            canonical = wiki_title
        print(f"[component] Wikipedia hit for '{name}'")
    except HTTPException:
        print(f"[component] no Wikipedia page for '{name}', continuing to scraper")

    # 4. Scrape specs only for unknown components
    if not dataset_entry:
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

    # 5. OpenRouter — two modes depending on what we found
    ai_generated = False

    if description or any(specs.values()):
        # 5a. We have some data — AI explains it in plain English
        print(f"[component] generating AI explanation for '{canonical}'")
        ai_explanation = await explain_component(canonical, specs, description)
        final_description = ai_explanation if ai_explanation else description

    else:
        # 5b. Everything failed — AI generates specs from its own knowledge
        print(f"[component] no data found, asking AI to generate for '{canonical}'")
        ai_data = await generate_component(canonical)

        if not ai_data:
            # AI also doesn't know it — genuine 404
            raise HTTPException(
                status_code=404,
                detail=f"'{name}' not found. Try a more specific component name."
            )

        # Use AI-generated data
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

    # 6. Build + cache
    source = "dataset" if dataset_entry else ("ai" if ai_generated else "live")
    result = {
        "name":          canonical,
        "description":   final_description,
        "specs":         specs,
        "datasheet_url": datasheet_url,
        "source":        source,
    }

    database.save_component(result)

    # Cache under original search term too
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

    # Dataset returned nothing → ask AI for alternatives
    if not found:
        print(f"[alternatives] no dataset matches for '{canonical}', asking AI")
        found = await generate_alternatives(canonical, specs)

    return {"component": canonical, "specs": specs, "alternatives": found}


@app.get("/health")
async def health():
    return {
        "status":       "ok",
        "phase":        "3.3",
        "openrouter":   "enabled",
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
    """Strip package suffixes for better Wikipedia matches."""
    import re
    simplified = re.sub(r'[-/][A-Z]{1,4}$', '', name.strip())
    simplified = re.sub(r'[A-Z]\d[A-Z]\d?$', '', simplified)
    return simplified.strip('-') or name


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
        raise HTTPException(status_code=504, detail="Wikipedia request timed out.")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Wikipedia returned {r.status_code}.")

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