"""
BXP Health Risk Index (HRI) and server-side quality assessment.

Pure functions, no web-framework imports, so they can be unit-tested and reused
without starting the server. SPEC.md section 13 defines the HRI; sdk/python and
sdk/typescript implement the same formula and are cross-checked by
conformance/hri_vectors.json.
"""

import time

# Wire-protocol version this node speaks (major.minor; SPEC.md section 5.8).
BXP_VERSION = "2.0"

# ─── Agent ID normalisation ───────────────────────────────────
AGENT_ID_MAP = {
    "PM2_5": "pm25", "PM10": "pm10", "NO2": "no2",
    "O3":    "o3",   "CO":   "co",   "SO2": "so2",
}

WHO_THRESHOLDS = {
    "pm25": 15.0, "pm10": 45.0, "no2": 25.0,
    "o3": 100.0, "co": 4.0, "so2": 40.0
}

WEIGHTS = {
    "pm25": 0.35, "pm10": 0.15, "no2": 0.15,
    "o3": 0.12, "co": 0.10, "so2": 0.05
}

# ─── Pydantic models ──────────────────────────────────────────


def calculate_hri(
    readings: dict,
    duration: str = "1h",
    population: str = "general",
) -> float:
    """
    Calculate BXP_HRI with duration and population factors.
    duration:   "1h" | "8h" | "24h"
    population: "general" | "sensitive"
    """
    d_factor = {"1h": 1.0, "8h": 1.2, "24h": 1.5}.get(duration, 1.0)
    v_factor = {"general": 1.0, "sensitive": 1.3}.get(population, 1.0)
    score = 0.0
    for agent, weight in WEIGHTS.items():
        val = readings.get(agent)
        thresh = WHO_THRESHOLDS.get(agent)
        if val is not None and thresh:
            normalized = min(float(val) / thresh, 1.0)
            score += normalized * weight
    return round(min(score * 100 * d_factor * v_factor, 100), 2)  # 2 dp, as SPEC.md 13.3 and the SDKs


def hri_level(hri: float) -> str:
    if hri <= 20: return "CLEAN"
    if hri <= 40: return "MODERATE"
    if hri <= 60: return "ELEVATED"
    if hri <= 75: return "HIGH"
    if hri <= 90: return "VERY_HIGH"
    return "HAZARDOUS"


def hri_color(hri: float) -> str:
    if hri <= 20: return "#00E676"
    if hri <= 40: return "#FFEB3B"
    if hri <= 60: return "#FF9800"
    if hri <= 75: return "#F44336"
    if hri <= 90: return "#9C27B0"
    return "#4A0000"


def hri_advice(level: str) -> str:
    return {
        "CLEAN":     "Air quality is excellent. Enjoy outdoor activities freely.",
        "MODERATE":  "Air quality is acceptable. Sensitive individuals should limit prolonged outdoor exertion.",
        "ELEVATED":  "Sensitive groups should reduce prolonged outdoor exertion.",
        "HIGH":      "Everyone should reduce prolonged outdoor exertion. Sensitive groups stay indoors.",
        "VERY_HIGH": "Avoid outdoor activities. Sensitive groups must stay indoors.",
        "HAZARDOUS": "Health emergency. Everyone should avoid all outdoor activity.",
    }.get(level, "")


def assess_quality(agents_dict: dict, timestamp_us: int) -> dict:
    notes = []
    now_us = int(time.time() * 1_000_000)

    if not agents_dict:
        return {"flag": "INVALID", "confidence": 0.0,
                "qcMethod": "server-auto", "notes": ["No agents present"]}

    if timestamp_us > now_us + 3_600_000_000:
        notes.append("Timestamp is in the future")
        return {"flag": "SUSPECT", "confidence": 0.3,
                "qcMethod": "server-auto", "notes": notes}

    any_exceeds = critical = False
    for key, val in agents_dict.items():
        if val is None:
            continue
        thr = WHO_THRESHOLDS.get(key)
        if thr is None:
            continue
        if float(val) > thr:
            any_exceeds = True
        if float(val) > thr * 5:
            critical = True
            notes.append(f"{key}={val} exceeds 5× WHO threshold ({thr})")

    if critical:
        return {"flag": "SUSPECT", "confidence": 0.4,
                "qcMethod": "server-auto", "notes": notes}

    confidence = 0.75 if any_exceeds else 0.90
    return {"flag": "UNVALIDATED", "confidence": confidence,
            "qcMethod": "server-auto", "notes": notes or None}
