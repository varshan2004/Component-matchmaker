"""
alternatives.py — Rule-based alternative component suggestion engine.

Stage 1 (filter): broad type group matching
  - LDO, linear, adjustable, positive, negative regulators → all "regulator" family
  - NPN small-signal + power → all "transistor_npn"
Stage 2 (score):  voltage + current + power proximity
Stage 3 (reason): human-readable explanation
"""

import re
import json
from pathlib import Path

_DATASET_PATH = Path(__file__).parent / "components_data.json"
with open(_DATASET_PATH) as f:
    DATASET: dict = json.load(f)


# ── Type Grouping ─────────────────────────────────────────────────────────────

def type_group(t: str) -> str:
    """Map raw type string → canonical group. Broad matching to maximise alternatives found."""
    t = t.lower().strip()

    # Diodes — most specific first
    if "schottky"      in t: return "diode_schottky"
    if "zener"         in t: return "diode_zener"
    if "tvs"           in t: return "diode_tvs"
    if "signal diode"  in t: return "diode_signal"
    if "rectifier"     in t: return "diode_rectifier"
    if "diode"         in t: return "diode_rectifier"  # generic → rectifier bucket

    # MOSFETs
    if "n-channel" in t or "nmos" in t: return "mosfet_n"
    if "p-channel" in t or "pmos" in t: return "mosfet_p"
    if "mosfet"    in t:                return "mosfet_n"   # default to N

    # Transistors — group small-signal + power together for better matching
    if "darlington" in t and "npn" in t: return "transistor_npn"
    if "darlington" in t and "pnp" in t: return "transistor_pnp"
    if "darlington" in t:                return "transistor_npn"
    if "npn"        in t:                return "transistor_npn"
    if "pnp"        in t:                return "transistor_pnp"
    if "bjt"        in t or "bipolar" in t: return "transistor_npn"
    if "transistor" in t:                return "transistor_npn"

    # Op-amps / comparators
    if "op-amp"  in t or "opamp" in t or "operational" in t: return "opamp"
    if "comparator" in t:                return "opamp"     # close enough for alternatives
    if "amplifier"  in t:                return "opamp"

    # Regulators — ALL in one bucket for maximum cross-matching
    # (AMS1117 LDO ↔ LM7805 linear ↔ LM317 adjustable are all valid swaps)
    if any(k in t for k in [
        "regulator","ldo","dropout","shunt","reference",
        "buck","boost","switching","step-down","step-up"
    ]): return "regulator"

    # Timers / oscillators
    if "timer"  in t or "oscillator" in t: return "timer"

    # Motor drivers
    if "motor"  in t or "h-bridge"   in t or "stepper" in t: return "motor_driver"

    # Digital / logic
    if "shift register" in t: return "shift_register"
    if "multiplexer"    in t or "mux" in t: return "multiplexer"
    if "gate"           in t or "inverter" in t or "logic" in t: return "logic"
    if "io expander"    in t or "io expand" in t: return "io_expander"
    if "pwm"            in t: return "pwm_controller"
    if "adc"            in t: return "adc"
    if "dac"            in t: return "dac"

    # MCUs — group all 8-bit together, 32-bit together
    if "32-bit" in t or "arm" in t or "cortex" in t: return "mcu_32"
    if "8-bit"  in t or "microcontroller" in t:       return "mcu_8"
    if "wifi"   in t or "ble" in t or "bluetooth" in t: return "mcu_wireless"

    # Sensors
    if "temperature sensor" in t: return "sensor_temp"
    if "imu"    in t or "accelerometer" in t or "gyro" in t: return "sensor_imu"
    if "sensor" in t: return "sensor"

    # Communication
    if "rs-232" in t or "rs232" in t: return "transceiver_uart"
    if "rs-485" in t or "rs485" in t: return "transceiver_rs485"
    if "can"    in t:                 return "transceiver_can"
    if "transceiver" in t:            return "transceiver_uart"

    # Optocouplers
    if "opto"   in t or "optocoupler" in t: return "optocoupler"

    # Audio
    if "audio"  in t: return "audio_amp"

    # Charger / power management
    if "charger" in t or "battery" in t: return "charger"

    return t[:30]   # fallback — use raw type as group


# ── Value Parsers ─────────────────────────────────────────────────────────────

def parse_voltage(v: str) -> float | None:
    if not v: return None
    v = v.replace("±","").replace("-","to").strip()
    m = re.search(r"([\d]+(?:\.[\d]+)?)", v)
    return float(m.group(1)) if m else None


def parse_current(c: str) -> float | None:
    if not c: return None
    m = re.search(r"([\d]+(?:\.[\d]+)?)\s*m[Aa]", c)
    if m: return float(m.group(1)) / 1000
    m = re.search(r"([\d]+(?:\.[\d]+)?)\s*[Aa]", c)
    return float(m.group(1)) if m else None


def parse_power(p: str) -> float | None:
    if not p: return None
    m = re.search(r"([\d]+(?:\.[\d]+)?)\s*m[Ww]", p)
    if m: return float(m.group(1)) / 1000
    m = re.search(r"([\d]+(?:\.[\d]+)?)\s*[Ww]", p)
    return float(m.group(1)) if m else None


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(target_v, target_i, target_p, cand: dict) -> tuple[int, list[str]]:
    score, reasons = 0, []

    cand_v = parse_voltage(cand.get("voltage",""))
    cand_i = parse_current(cand.get("current",""))
    cand_p = parse_power(cand.get("power",""))

    # Voltage
    if target_v and cand_v:
        diff = abs(target_v - cand_v) / target_v
        if diff == 0:
            score += 35; reasons.append(f"same {cand['voltage']} voltage")
        elif diff <= 0.10:
            score += 25; reasons.append(f"very close voltage ({cand['voltage']})")
        elif diff <= 0.30:
            score += 15; reasons.append(f"similar voltage ({cand['voltage']})")
        elif diff <= 0.60:
            score += 6;  reasons.append(f"different voltage ({cand['voltage']})")
    elif cand_v:
        score += 3

    # Current
    if target_i and cand_i:
        ratio = min(cand_i, target_i) / max(cand_i, target_i)
        if ratio >= 0.90:
            score += 25; reasons.append(f"matching current ({cand['current']})")
        elif ratio >= 0.60:
            score += 15; reasons.append(f"comparable current ({cand['current']})")
        elif cand_i > target_i:
            score += 8;  reasons.append(f"higher current capacity ({cand['current']})")
        else:
            score += 4;  reasons.append(f"lower current rating ({cand['current']})")

    # Power (bonus)
    if target_p and cand_p:
        ratio = min(cand_p, target_p) / max(cand_p, target_p)
        if ratio >= 0.80:
            score += 10; reasons.append(f"similar power rating ({cand['power']})")
        elif cand_p > target_p:
            score += 5;  reasons.append(f"higher power dissipation ({cand['power']})")

    # Package match (bonus)
    if cand.get("package") and cand.get("package") == cand.get("package"):
        score += 5

    return score, reasons


def _build_reason(comp: dict, parts: list) -> str:
    base = comp.get("type", "Component")
    if parts:
        return f"{base} — {', '.join(parts[:2])}"
    return base


# ── Main Entry Point ──────────────────────────────────────────────────────────

def find_alternatives(name: str, specs: dict, top_n: int = 4) -> list[dict]:
    target_group = type_group(specs.get("type",""))
    target_v     = parse_voltage(specs.get("voltage",""))
    target_i     = parse_current(specs.get("current",""))
    target_p     = parse_power(specs.get("power",""))

    candidates = []

    for key, comp in DATASET.items():
        if key.upper() == name.upper():
            continue

        comp_group = type_group(comp.get("type",""))

        # Stage 1: type group must match
        if comp_group != target_group:
            continue

        # Stage 2: score
        score, parts = _score(target_v, target_i, target_p, comp)
        if score < 5:
            continue

        candidates.append({
            "name":    comp["name"],
            "type":    comp.get("type",""),
            "voltage": comp.get("voltage",""),
            "current": comp.get("current",""),
            "power":   comp.get("power",""),
            "reason":  _build_reason(comp, parts),
            "_score":  score,
        })

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    return [{k:v for k,v in c.items() if k!="_score"} for c in candidates[:top_n]]