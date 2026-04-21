"""
Smart Component Information System — Phase 3
Fixes: dataset-first lookup (no more Wikipedia redirects for known parts)
New:   GET /alternatives?name= endpoint

Resolution flow for /component:
  1. SQLite cache hit?       → return immediately
  2. Local dataset match?    → use those specs + datasheet
  3. Wikipedia API           → description text
  4. Wikipedia scraper       → supplementary specs (only if not in dataset)
  5. Save → SQLite → return
"""

import json
import httpx
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import database
import scraper
import alternatives as alt_engine

app = FastAPI(title="Smart Component Information System", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "SmartComponentSystem/1.0 (educational; contact@example.com)"}

# Load local component dataset on startup
_DATASET_PATH = Path(__file__).parent / "components_data.json"
with open(_DATASET_PATH) as f:
    COMPONENT_DATASET: dict = json.load(f)


@app.on_event("startup")
def on_startup():
    database.init_db()
    print(f"[startup] DB ready | dataset has {len(COMPONENT_DATASET)} components")


# ── /component ────────────────────────────────────────────────────────────────

@app.get("/component")
async def get_component(name: str = Query(..., min_length=1)):
    """
    GET /component?name=LM7805
    Returns: name, description, specs, datasheet_url, source
    """
    # 1. Cache check
    cached = database.get_cached(name)
    if cached:
        print(f"[component] cache hit: '{name}'")
        return cached

    # 2. Dataset lookup (case-insensitive, exact match first)
    dataset_entry = _dataset_lookup(name)
    specs         = {}
    datasheet_url = ""

    if dataset_entry:
        print(f"[component] dataset hit: '{name}' → {dataset_entry['name']}")
        specs         = {
            "type":    dataset_entry.get("type", ""),
            "voltage": dataset_entry.get("voltage", ""),
            "current": dataset_entry.get("current", ""),
        }
        datasheet_url = dataset_entry.get("datasheet_url", "")
        canonical     = dataset_entry["name"]
    else:
        canonical = name

    # 3. Wikipedia description
    description, wiki_title = await _fetch_wikipedia_description(canonical)

    # 4. Scrape Wikipedia only if dataset had no specs
    if not dataset_entry:
        scraped       = await scraper.scrape_component(canonical)
        scraped_specs = scraped.get("specs", {})
        specs = {
            "type":    scraped_specs.get("type", ""),
            "voltage": scraped_specs.get("voltage", ""),
            "current": scraped_specs.get("current", ""),
        }
        datasheet_url = scraped.get("datasheet_url", "") or \
            f"https://www.alldatasheet.com/search/?q={canonical.replace(' ', '+')}"

    # 5. Build + cache + return
    result = {
        "name":          wiki_title or canonical,
        "description":   description,
        "specs":         specs,
        "datasheet_url": datasheet_url,
        "source":        "dataset" if dataset_entry else "live",
    }

    database.save_component(result)
    return result


# ── /alternatives ─────────────────────────────────────────────────────────────

@app.get("/alternatives")
async def get_alternatives(name: str = Query(..., min_length=1)):
    """
    GET /alternatives?name=LM7805
    Returns top alternatives from dataset based on type + voltage + current match.
    """
    # Try dataset first for specs
    dataset_entry = _dataset_lookup(name)
    if dataset_entry:
        specs = {
            "type":    dataset_entry.get("type", ""),
            "voltage": dataset_entry.get("voltage", ""),
            "current": dataset_entry.get("current", ""),
        }
        canonical = dataset_entry["name"]
    else:
        # Try cache
        cached = database.get_cached(name)
        if cached:
            specs     = cached.get("specs", {})
            canonical = cached.get("name", name)
        else:
            # Fetch live
            try:
                comp = await get_component(name)
                specs     = comp.get("specs", {})
                canonical = comp.get("name", name)
            except HTTPException:
                raise HTTPException(
                    status_code=404,
                    detail=f"Cannot find specs for '{name}' to suggest alternatives."
                )

    found = alt_engine.find_alternatives(canonical, specs, top_n=4)

    return {
        "component":   canonical,
        "specs":       specs,
        "alternatives": found,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "phase": 3, "dataset_size": len(COMPONENT_DATASET)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dataset_lookup(name: str) -> dict | None:
    """Case-insensitive exact match against local dataset."""
    key = name.strip().upper()
    for k, v in COMPONENT_DATASET.items():
        if k.upper() == key:
            return v
    return None


async def _fetch_wikipedia_description(name: str) -> tuple[str, str]:
    """Fetch plain-text intro from Wikipedia. Returns (description, canonical_title)."""
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
        raise HTTPException(
            status_code=404,
            detail=f"'{name}' not found on Wikipedia. Try a more specific name."
        )

    page    = next(iter(pages.values()))
    extract = page.get("extract", "").strip()

    if not extract:
        raise HTTPException(status_code=404, detail=f"No description found for '{name}'.")

    sentences  = [s.strip() for s in extract.split(".") if s.strip()]
    short_desc = ". ".join(sentences[:3]) + "."

    return short_desc, page.get("title", name)