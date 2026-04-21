"""
openrouter_api.py — OpenRouter AI layer.

Two modes:
  1. explain_component()  — plain-English description using collected data
  2. generate_component() — full specs from AI knowledge when everything else fails
"""

import httpx
import json

API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = "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"
MODEL   = "openai/gpt-4o-mini"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
    "HTTP-Referer":  "http://localhost:5173",
    "X-Title":       "Smart Component System",
}

# Exact type names that match alternatives.py type_group() keywords
# AI must pick from this list so alternatives engine can match them
VALID_TYPES = (
    "N-Channel MOSFET, P-Channel MOSFET, "
    "NPN Transistor, PNP Transistor, NPN Power Transistor, PNP Power Transistor, "
    "Positive Voltage Regulator, Negative Voltage Regulator, Adjustable Voltage Regulator, "
    "Op-Amp, Timer IC, "
    "Rectifier Diode, Signal Diode, Schottky Diode, Zener Diode, "
    "8-bit Microcontroller, 32-bit Microcontroller, WiFi Microcontroller, "
    "Motor Driver IC, Audio Amplifier IC, ADC IC, DAC IC, Other"
)


async def explain_component(name: str, specs: dict, raw_description: str = "") -> str:
    """
    Generate plain-English explanation using collected data as context.
    Returns explanation string or "" on failure.
    """
    spec_lines = []
    if specs.get("type"):    spec_lines.append(f"Type: {specs['type']}")
    if specs.get("voltage"): spec_lines.append(f"Voltage: {specs['voltage']}")
    if specs.get("current"): spec_lines.append(f"Current: {specs['current']}")

    spec_text = "\n".join(spec_lines) if spec_lines else "No specs available"
    context   = raw_description.strip() if raw_description else "No additional data"

    prompt = (
        f'Explain the electronic component "{name}" in simple terms for an engineer.\n'
        f"Include:\n"
        f"- What it is and what it does\n"
        f"- Its key specs and what they mean practically\n"
        f"- Typical use cases\n"
        f"- Where to buy it (mention Digi-Key or Mouser)\n\n"
        f"Available data:\n{spec_text}\n\n"
        f"Additional context:\n{context}\n\n"
        f"Keep the response under 120 words. Be direct and practical."
    )

    return await _call_openrouter(prompt, name, mode="explain")


async def generate_component(name: str) -> dict:
    """
    Generate full component data from AI knowledge alone.
    Used when dataset + Wikipedia + scraper all return nothing.
    Returns { description, specs: {type, voltage, current}, datasheet_url }
    or empty dict on failure.
    """
    prompt = (
        f'You are an electronics component database. Return data for: "{name}"\n\n'
        f"Respond ONLY with a valid JSON object. No explanation, no markdown, no code fences:\n"
        f'{{\n'
        f'  "description": "2-3 sentence plain English explanation",\n'
        f'  "type": "pick EXACTLY one: {VALID_TYPES}",\n'
        f'  "voltage": "voltage rating e.g. 55V or 3.3-5V",\n'
        f'  "current": "current rating e.g. 47A or 300mA",\n'
        f'  "datasheet_url": "direct PDF URL if confident, else empty string"\n'
        f'}}\n\n'
        f'If you have never heard of this component, return: {{"unknown": true}}'
    )

    raw = await _call_openrouter(prompt, name, mode="generate")
    if not raw:
        return {}

    # Strip markdown code fences if model adds them anyway
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw   = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[openrouter] JSON parse failed for '{name}': {raw[:120]}")
        return {}

    if data.get("unknown"):
        print(f"[openrouter] AI does not know '{name}'")
        return {}

    print(f"[openrouter] AI generated data for '{name}': type={data.get('type')} v={data.get('voltage')} i={data.get('current')}")

    return {
        "description":   data.get("description", ""),
        "specs": {
            "type":    data.get("type", ""),
            "voltage": data.get("voltage", ""),
            "current": data.get("current", ""),
        },
        "datasheet_url": data.get("datasheet_url", ""),
    }


async def _call_openrouter(prompt: str, name: str, mode: str) -> str:
    """Shared async HTTP call to OpenRouter. Returns content string or ""."""
    payload = {
        "model":       MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens":  300,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(API_URL, json=payload, headers=HEADERS)
            r.raise_for_status()
            data = r.json()

        content = (
            data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
        )
        print(f"[openrouter] {mode} for '{name}' → {len(content)} chars")
        return content

    except httpx.HTTPStatusError as e:
        print(f"[openrouter] HTTP {e.response.status_code} for '{name}': {e.response.text[:200]}")
        return ""
    except Exception as e:
        print(f"[openrouter] error for '{name}': {e}")
        return ""


async def generate_alternatives(name: str, specs: dict) -> list:
    """
    Generate alternative components using AI when dataset has no matches.
    Returns list of {name, type, voltage, current, reason} or [] on failure.
    """
    spec_text = ", ".join(f"{k}: {v}" for k, v in specs.items() if v)

    prompt = f"""You are an electronics component database.
Suggest 3-4 alternative components for: "{name}"
Specs: {spec_text if spec_text else "unknown"}

Respond ONLY with a valid JSON array, no explanation, no markdown:
[
  {{
    "name": "part number",
    "type": "component type",
    "voltage": "voltage rating",
    "current": "current rating",
    "reason": "one sentence why this is a good alternative"
  }}
]

Only suggest real, commonly available components. If you don't know any alternatives, return []."""

    raw = await _call_openrouter(prompt, name, mode="alternatives")
    if not raw:
        return []

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            print(f"[openrouter] {len(data)} AI alternatives for '{name}'")
            return data
    except json.JSONDecodeError:
        print(f"[openrouter] failed to parse alternatives JSON for '{name}'")

    return []