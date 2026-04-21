"""
normalizer.py — Standardize raw spec strings to consistent engineering format.
Examples:
  "5 volts"  → "5V"
  "5 v"      → "5V"
  "100 milliamps" → "100mA"
  "0.1 A"    → "0.1A"
"""

import re


def normalize_voltage(raw: str) -> str:
    if not raw:
        return ""
    raw = " ".join(raw.split())

    # Match patterns like: 1.5–5.5 V, 5V, 3.3 volts, 12 volt
    # Capture first number in a range
    m = re.search(
        r'([\d]+(?:[.,][\d]+)?)\s*(?:to|–|-|~)?\s*[\d]*(?:[.,][\d]*)?\s*'
        r'(k(?:ilo)?)?v(?:olts?)?\b',
        raw, re.IGNORECASE
    )
    if m:
        num = m.group(1).replace(",", ".")
        prefix = "k" if m.group(2) else ""
        return f"{num}{prefix}V"

    return _trim(raw)


def normalize_current(raw: str) -> str:
    if not raw:
        return ""
    raw = " ".join(raw.split())

    # milliamps first (must check before amps)
    m = re.search(r'([\d]+(?:[.,][\d]+)?)\s*m(?:illi)?a(?:mps?|mperes?)?\b', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1).replace(',', '.')}mA"

    # microamps
    m = re.search(r'([\d]+(?:[.,][\d]+)?)\s*(?:µ|u|micro)a(?:mps?|mperes?)?\b', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1).replace(',', '.')}µA"

    # amps
    m = re.search(r'([\d]+(?:[.,][\d]+)?)\s*a(?:mps?|mperes?)?\b', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1).replace(',', '.')}A"

    return _trim(raw)


def normalize_type(raw: str) -> str:
    if not raw:
        return ""
    # Clean Wikipedia footnote markers like [1], [a]
    raw = re.sub(r'\[\w+\]', '', raw).strip()
    # Take only first line / sentence if multi-line
    raw = raw.split("\n")[0].split(";")[0].strip()
    return _trim(raw, max_len=80)


def normalize_spec(value: str, spec_type: str) -> str:
    """Route to correct normalizer based on spec type."""
    if not value:
        return ""
    if spec_type == "voltage":
        return normalize_voltage(value)
    if spec_type == "current":
        return normalize_current(value)
    if spec_type == "type":
        return normalize_type(value)
    return _trim(value)


def _trim(s: str, max_len: int = 60) -> str:
    s = s.strip()
    return s[:max_len] + "…" if len(s) > max_len else s