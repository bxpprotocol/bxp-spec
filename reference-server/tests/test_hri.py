"""Pure-function tests for hri.py (no web framework needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hri  # noqa: E402


def test_zero_is_clean_and_pm25_at_threshold_contributes_its_weight():
    assert hri.calculate_hri({"pm25": 0}) == 0.0
    assert hri.calculate_hri({"pm25": 15.0}) == 35.0
    assert hri.calculate_hri({"pm25": 500.0}) == 35.0  # capped per agent


def test_all_six_agents_at_threshold_and_result_is_capped():
    # The six agents the node ingests carry 0.92 of SPEC.md 13.2's total weight
    # (the remainder belongs to agents this node does not compute), so 92 is the
    # honest maximum here; the duration/vulnerability modifiers cap at 100.
    full = {"pm25": 15, "pm10": 45, "no2": 25, "o3": 100, "co": 4, "so2": 40}
    assert hri.calculate_hri(full) == 92.0
    assert hri.calculate_hri(full, "24h", "sensitive") == 100.0


def test_level_boundaries():
    assert [hri.hri_level(x) for x in (0, 20, 20.1, 40, 60, 75, 90, 90.1)] == [
        "CLEAN", "CLEAN", "MODERATE", "MODERATE", "ELEVATED", "HIGH", "VERY_HIGH", "HAZARDOUS"]


def test_quality_assessment():
    now_us = 1_800_000_000_000_000
    assert hri.assess_quality({}, now_us)["flag"] == "INVALID"
    assert hri.assess_quality({"pm25": 10}, int(__import__("time").time() * 1e6))["flag"] == "UNVALIDATED"
    future = int((__import__("time").time() + 7200) * 1e6)
    assert hri.assess_quality({"pm25": 10}, future)["flag"] == "SUSPECT"
    assert hri.assess_quality({"pm25": 15 * 6}, int(__import__("time").time() * 1e6))["flag"] == "SUSPECT"
