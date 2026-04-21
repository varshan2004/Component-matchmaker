"""
alternatives.py — Rule-based alternative component suggestion engine.

Stage 1 (filter): same type group (NPN stays NPN, N-Ch MOSFET stays N-Ch, etc.)
Stage 2 (score):  voltage proximity + current proximity → ranked top-N
Stage 3 (reason): human-readable explanation per result
"""

import re
import json
from pathlib import Path

# Load dataset once at import time
_DATASET_PATH = Path(__file__).parent / "components_data.json"
with open(_DATASET_PATH) as f:
    DATASET: dict = json.load(f)


# ── Type Grouping ─────────────────────────────────────────────────────────────

def type_group(t: str) -> str:
    """Map raw type string to a canonical group for filtering."""
    t = t.lower()
    if "schottky"          in t: return "schottky_diode"
    if "signal diode"      in t: return "signal_diode"
    if "diode"             in t: return "diode"
    if "n-channel"         in t or "n channel" in t: return "mosfet_n"
    if "p-channel"         in t or "p channel" in t: return "mosfet_p"
    if "mosfet"            in t: return "mosfet"
    if "npn"               in t: return "transistor_npn"
    if "pnp"               in t: return "transistor_pnp"
    if "op-amp"            in t or "opamp" in t or "operational" in t: return "opamp"
    if "timer"             in t: return "timer"
    # Regulators split into 3 sub-groups so positive/negative never cross-match
    if "negative"          in t and "regulator" in t: return "regulator_negative"
    if "adjustable"        in t and "regulator" in t: return "regulator_adjustable"
    if "regulator"         in t: return "regulator_positive"
    return t.strip()


# ── Value Parsers ─────────────────────────────────────────────────────────────

def parse_voltage(v: str) -> float | None:
    """Parse voltage string to absolute float (V). Returns None if not parseable."""
    if not v:
        return None
    v = v.replace("±", "").strip()
    # Take first number in string (handles "1.25-37V", "4.5-16V", "5V")
    m = re.search(r"([\d]+(?:\.[\d]+)?)", v)
    if m:
        return float(m.group(1))
    return None


def parse_current(c: str) -> float | None:
    """Parse current string to float in Amps. Returns None if not parseable."""
    if not c:
        return None
    c = c.strip()
    m_ma = re.search(r"([\d]+(?:\.[\d]+)?)\s*m[Aa]", c)
    if m_ma:
        return float(m_ma.group(1)) / 1000
    m_a = re.search(r"([\d]+(?:\.[\d]+)?)\s*[Aa]", c)
    if m_a:
        return float(m_a.group(1))
    return None


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(target_v: float | None, target_i: float | None,
           cand: dict) -> tuple[int, list[str]]:
    """Return (score, reason_parts) for one candidate vs target specs."""
    reasons = []
    score   = 0

    cand_v = parse_voltage(cand.get("voltage", ""))
    cand_i = parse_current(cand.get("current", ""))

    # Voltage scoring
    if target_v is not None and cand_v is not None:
        diff = abs(target_v - cand_v)
        pct  = diff / target_v if target_v else 1
        if diff == 0:
            score += 30
            reasons.append(f"same {cand['voltage']} output voltage")
        elif pct <= 0.10:
            score += 20
            reasons.append(f"very close voltage ({cand['voltage']})")
        elif pct <= 0.30:
            score += 12
            reasons.append(f"similar voltage ({cand['voltage']})")
        elif pct <= 0.60:
            score += 5
            reasons.append(f"different voltage ({cand['voltage']})")
    elif cand_v is not None:
        score += 5  # at least has a voltage spec

    # Current scoring
    if target_i is not None and cand_i is not None:
        ratio = min(cand_i, target_i) / max(cand_i, target_i) if max(cand_i, target_i) else 1
        if ratio >= 0.90:
            score += 20
            reasons.append(f"matching current rating ({cand['current']})")
        elif ratio >= 0.60:
            score += 12
            reasons.append(f"comparable current ({cand['current']})")
        elif cand_i > target_i:
            score += 6
            reasons.append(f"higher current capacity ({cand['current']})")
        else:
            score += 3
            reasons.append(f"lower current rating ({cand['current']})")

    return score, reasons


def _build_reason(comp: dict, reason_parts: list[str]) -> str:
    """Assemble final human-readable reason string."""
    base = f"{comp['type']}"
    if reason_parts:
        detail = ", ".join(reason_parts[:2])  # max 2 facts
        return f"{base} — {detail}"
    return base


# ── Main Entry Point ──────────────────────────────────────────────────────────

def find_alternatives(name: str, specs: dict, top_n: int = 4) -> list[dict]:
    """
    Given component name + its specs, return top_n alternatives from dataset.

    Steps:
      1. Determine type group of target component
      2. Filter dataset to same type group (exclude self)
      3. Score each candidate by voltage + current proximity
      4. Return top-N sorted by score
    """
    target_type  = specs.get("type", "")
    target_group = type_group(target_type)
    target_v     = parse_voltage(specs.get("voltage", ""))
    target_i     = parse_current(specs.get("current", ""))

    candidates = []

    for key, comp in DATASET.items():
        # Skip self
        if key.upper() == name.upper():
            continue

        # Stage 1: type group must match
        if type_group(comp.get("type", "")) != target_group:
            continue

        # Stage 2: score
        score, reason_parts = _score(target_v, target_i, comp)

        # Minimum score threshold — avoid totally irrelevant results
        if score < 5:
            continue

        candidates.append({
            "name":    comp["name"],
            "type":    comp["type"],
            "voltage": comp.get("voltage", ""),
            "current": comp.get("current", ""),
            "reason":  _build_reason(comp, reason_parts),
            "_score":  score,
        })

    # Sort by score descending
    candidates.sort(key=lambda x: x["_score"], reverse=True)

    # Strip internal score field
    return [
        {k: v for k, v in c.items() if k != "_score"}
        for c in candidates[:top_n]
    ]