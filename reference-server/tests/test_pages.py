"""
HTML pages must never reflect untrusted input as markup or script.

Everything here is untrusted: the city name comes from the URL, and the
location name / values / colours come from a third-party API. Stdlib-only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pages  # noqa: E402

PAYLOADS = ["<img src=x onerror=alert(1)>", "</script><script>alert(1)</script>",
            '"><svg onload=alert(1)>', "'-alert(1)-'"]


def hostile(payload):
    return {
        "bxp_hri": {"score": 12.0, "level": payload, "color": payload, "advice": payload},
        "location": {"name": payload, "query": payload, "latitude": float("nan"), "longitude": 1.0},
        "readings": {"pm25": payload, "pm10": 12, "no2": float("inf")},
        "timestamp": payload, "aqi": payload, "dominant_pollutant": payload,
        "attribution": payload,
    }


def _has_live_markup(html_text, payload):
    # A payload is "live" if any dangerous fragment appears unescaped.
    return any(frag in html_text for frag in ("<img src=x", "<svg onload", "</script><script>alert",
                                              "onerror=alert(1)>", '"><svg'))


def test_dashboard_escapes_every_untrusted_field():
    for p in PAYLOADS:
        assert not _has_live_markup(pages.render_dashboard(hostile(p)), p), p


def test_widget_and_error_pages_escape_input():
    for p in PAYLOADS:
        assert not _has_live_markup(pages.widget_page(hostile(p), p), p)
        assert not _has_live_markup(pages.widget_missing_page(p), p)
        assert not _has_live_markup(pages.not_found_page(p), p)


def test_nan_coordinates_do_not_produce_invalid_javascript():
    out = pages.render_dashboard(hostile("x"))
    assert "NaN" not in out and "Infinity" not in out


def test_bad_css_colour_falls_back_instead_of_injecting_css():
    out = pages.widget_page(hostile("red;}</style><script>"), "x")
    assert "</style><script>" not in out


def test_non_numeric_upstream_value_renders_na_not_a_crash():
    data = hostile("x")
    data["readings"] = {"pm25": "n/a", "pm10": None, "no2": float("nan")}
    assert "N/A" in pages.render_dashboard(data)


def test_js_json_cannot_break_out_of_a_script_tag():
    out = pages.js_json({"a": "</script><!--", "b": "\u2028"})
    assert "</script>" not in out and "<!--" not in out and "\u2028" not in out
