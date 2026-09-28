"""
HTML pages served by the reference node (landing page, dashboard, map,
compare, embeddable widget).

Kept separate from server.py so the HTML can be tested without FastAPI.
SECURITY: every value interpolated into HTML or into an inline <script> MUST go
through esc() / js_str() / js_json() below -- never interpolate request data or
upstream API data directly. tests/test_pages.py enforces this.
"""

import html
import json
import math
import re
from urllib.parse import quote

from hri import BXP_VERSION, WHO_THRESHOLDS


def esc(value) -> str:
    """HTML-escape any value for use in element text or a quoted attribute."""
    return html.escape(str(value), quote=True)


def _finite(value):
    """Replace NaN/Infinity (not valid JSON) with None, recursively."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def js_json(value) -> str:
    """JSON safe to embed inside an inline <script> (no </script>, no <!--, no U+2028/9)."""
    return (json.dumps(_finite(value), default=str, allow_nan=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _num(value, default="null") -> str:
    """A finite number rendered for JS/HTML, else `default`."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return repr(f) if f == f and f not in (float("inf"), float("-inf")) else default


# Shared by every page that renders API-supplied strings via innerHTML/popups.
JS_ESC = "const esc = s => String(s ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"

# ─── Dashboard renderer ───────────────────────────────────────

def render_dashboard(data: dict) -> str:
    hri       = data["bxp_hri"]["score"]
    level     = data["bxp_hri"]["level"]
    color     = data["bxp_hri"]["color"]
    advice    = data["bxp_hri"]["advice"]
    location  = data["location"]["name"]
    readings  = data["readings"]
    timestamp = data["timestamp"]
    aqi       = data.get("aqi", "N/A")
    dominant  = (data.get("dominant_pollutant") or "").upper()
    query     = data["location"]["query"]
    raw_query, raw_color = str(query), str(color)
    # Everything below is interpolated into HTML: escape once, here.
    location, level, advice, aqi = esc(location), esc(level), esc(advice), esc(aqi)
    dominant, timestamp, hri = esc(dominant), esc(timestamp), esc(hri)
    url_query = quote(raw_query, safe="")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", raw_color):
        raw_color = "#00d4ff"
    color = raw_color
    query = esc(raw_query)

    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        rgb = f"{r},{g},{b}"
    except Exception:
        rgb = "0,212,255"

    def reading_card(label, key, unit):
        val = readings.get(key)
        try:  # upstream data is untrusted: a non-numeric value renders as N/A, not a 500
            if val is not None and not math.isfinite(float(val)):
                val = None
            elif val is not None:
                float(val)
        except (TypeError, ValueError):
            val = None
        if val is None:
            return f'''<div class="r-card">
<span class="r-label">{label}</span>
<span class="r-val na">N/A</span>
<div class="r-bar-bg"><div class="r-bar" style="width:0%"></div></div>
<span class="r-who">WHO: {WHO_THRESHOLDS.get(key,"—")} {unit}</span>
</div>'''
        thresh = WHO_THRESHOLDS.get(key, 100)
        pct    = min(int((float(val) / thresh) * 100), 100)
        bar_color = "#00E676" if pct < 50 else "#FF9800" if pct < 100 else "#F44336"
        return f'''<div class="r-card">
<span class="r-label">{label}</span>
<span class="r-val">{esc(val)}<span class="r-unit"> {unit}</span></span>
<div class="r-bar-bg"><div class="r-bar" style="width:{pct}%;background:{bar_color}"></div></div>
<span class="r-who">WHO threshold: {thresh} {unit}</span>
</div>'''

    cards = "".join([
        reading_card("PM2.5", "pm25", "μg/m³"),
        reading_card("PM10",  "pm10", "μg/m³"),
        reading_card("NO₂",   "no2",  "μg/m³"),
        reading_card("O₃",    "o3",   "μg/m³"),
        reading_card("CO",    "co",   "mg/m³"),
        reading_card("SO₂",   "so2",  "μg/m³"),
    ])

    dominant_pill = f'<span class="meta-pill">Dominant: {dominant}</span>' if dominant else ""

    # JSON for export button
    export_json = js_json({k: v for k, v in data.items() if not k.startswith("_")})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — {location} Air Quality</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#060b18;--surface:#0d1628;--border:#1a2540;
  --text:#e8edf5;--muted:#4a5568;--accent:#00d4ff;
  --hri:{color};--rgb:{rgb};
}}
body{{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;min-height:100vh;
  background-image:radial-gradient(ellipse at 15% 15%,rgba(0,212,255,0.03) 0%,transparent 50%),
    radial-gradient(ellipse at 85% 85%,rgba(var(--rgb),0.06) 0%,transparent 50%);}}
header{{padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);background:rgba(6,11,24,0.92);backdrop-filter:blur(12px);
  position:sticky;top:0;z-index:100;}}
.logo{{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}}
nav a{{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}}
nav a:hover{{color:var(--accent)}}
.main{{max-width:1100px;margin:0 auto;padding:3rem 2rem}}
.loc{{font-size:clamp(2rem,5vw,3.5rem);font-weight:800;letter-spacing:-0.02em;line-height:1;margin-bottom:0.4rem}}
.ts-row{{display:flex;align-items:center;gap:1rem;margin-bottom:2.5rem;flex-wrap:wrap}}
.ts{{font-family:'Space Mono',monospace;font-size:0.7rem;color:var(--muted)}}
.refresh-badge{{font-family:'Space Mono',monospace;font-size:0.65rem;color:#00E676;
  background:rgba(0,230,118,0.08);border:1px solid rgba(0,230,118,0.2);
  padding:0.2rem 0.6rem;border-radius:999px;cursor:pointer;transition:all 0.2s}}
.refresh-badge:hover{{background:rgba(0,230,118,0.15)}}
.hri-block{{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  padding:2.5rem;margin-bottom:2rem;display:grid;grid-template-columns:auto 1fr;gap:3rem;
  align-items:center;position:relative;overflow:hidden;}}
.hri-block::after{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--hri);}}
.score{{font-size:clamp(4rem,10vw,6.5rem);font-weight:800;font-family:'Space Mono',monospace;
  color:var(--hri);line-height:1;text-shadow:0 0 60px rgba(var(--rgb),0.4);}}
.level{{font-size:1.4rem;font-weight:700;color:var(--hri);margin-bottom:0.6rem;letter-spacing:0.05em}}
.advice{{font-size:0.95rem;color:#94a3b8;line-height:1.65;margin-bottom:1rem;max-width:480px}}
.pills{{display:flex;gap:0.75rem;flex-wrap:wrap;align-items:center}}
.meta-pill{{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.3rem 0.8rem;
  border:1px solid var(--border);border-radius:999px;color:var(--muted)}}
.export-btn{{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.3rem 0.8rem;
  border:1px solid var(--accent);border-radius:999px;color:var(--accent);
  cursor:pointer;background:transparent;transition:all 0.2s}}
.export-btn:hover{{background:rgba(0,212,255,0.1)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:0.85rem;margin-bottom:2.5rem;}}
.r-card{{background:var(--surface);border:1px solid var(--border);border-radius:1rem;padding:1.4rem;
  transition:border-color 0.2s,transform 0.15s;}}
.r-card:hover{{border-color:var(--accent);transform:translateY(-2px)}}
.r-label{{font-family:'Space Mono',monospace;font-size:0.65rem;color:var(--muted);
  letter-spacing:0.12em;text-transform:uppercase;display:block;margin-bottom:0.5rem}}
.r-val{{font-size:1.9rem;font-weight:800;font-family:'Space Mono',monospace;display:block;margin-bottom:0.65rem}}
.r-val.na{{color:var(--muted);font-size:1.4rem}}
.r-unit{{font-size:0.85rem;color:var(--muted);font-weight:400}}
.r-bar-bg{{height:3px;background:var(--border);border-radius:999px;margin-bottom:0.5rem}}
.r-bar{{height:3px;border-radius:999px}}
.r-who{{font-family:'Space Mono',monospace;font-size:0.6rem;color:var(--muted)}}
.section-title{{font-size:1rem;font-weight:700;color:var(--muted);letter-spacing:0.08em;
  text-transform:uppercase;margin-bottom:1rem;font-family:'Space Mono',monospace}}
.map-container{{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  overflow:hidden;height:300px;margin-bottom:2rem;}}
.chart-container{{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  padding:1.5rem;margin-bottom:2rem;}}
.search-row{{display:flex;gap:0;background:var(--surface);border:1px solid var(--border);
  border-radius:0.85rem;overflow:hidden;margin-bottom:3rem;transition:border-color 0.2s;}}
.search-row:focus-within{{border-color:var(--accent)}}
.s-input{{flex:1;background:transparent;border:none;outline:none;padding:1rem 1.25rem;
  color:var(--text);font-family:'Syne',sans-serif;font-size:1rem;}}
.s-input::placeholder{{color:var(--muted)}}
.s-btn{{background:var(--accent);color:#060b18;border:none;padding:1rem 1.75rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.9rem;cursor:pointer;
  transition:opacity 0.2s;white-space:nowrap;}}
.s-btn:hover{{opacity:0.85}}
footer{{border-top:1px solid var(--border);padding:1.5rem 2rem;text-align:center;
  max-width:1100px;margin:0 auto;}}
.fbadge{{display:inline-flex;align-items:center;gap:0.5rem;font-family:'Space Mono',monospace;
  font-size:0.65rem;color:var(--muted);text-decoration:none;border:1px solid var(--border);
  padding:0.4rem 1rem;border-radius:999px;transition:all 0.2s;}}
.fbadge:hover{{border-color:var(--accent);color:var(--accent)}}
.dot{{width:6px;height:6px;background:#00E676;border-radius:50%;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}
@media(max-width:640px){{
  .hri-block{{grid-template-columns:1fr;gap:1.5rem}}
  .score{{font-size:4rem}}
}}
</style>
</head>
<body>
<header>
  <span class="logo">BXP NODE</span>
  <nav>
    <a href="/dashboard">🔍 Search</a>
    <a href="/map">🗺 Map</a>
    <a href="/compare">⚖ Compare</a>
    <a href="/bxp/v2/city/{url_query}">JSON</a>
    <a href="/bxp/v2/health">Status</a>
    <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a>
  </nav>
</header>

<div class="main">
  <div class="loc">{location}</div>
  <div class="ts-row">
    <span class="ts" id="ts-label">Updated {timestamp[:19].replace("T"," ")} UTC · BXP v{BXP_VERSION} · {esc(data.get("attribution","AQICN"))}</span>
    <span class="refresh-badge" onclick="autoRefresh()" id="refresh-btn">⟳ Auto-refresh: OFF</span>
  </div>

  <div class="hri-block">
    <div class="score" id="hri-score">{hri}</div>
    <div>
      <div class="level" id="hri-level">{level}</div>
      <div class="advice" id="hri-advice">{advice}</div>
      <div class="pills">
        <span class="meta-pill">AQI {aqi}</span>
        {dominant_pill}
        <span class="meta-pill">BXP_HRI {hri}/100</span>
        <button class="export-btn" onclick="exportData()">↓ Export .bxp.json</button>
      </div>
    </div>
  </div>

  <div class="grid" id="readings-grid">{cards}</div>

  <div class="section-title">Location on Map</div>
  <div class="map-container" id="city-map"></div>

  <div class="section-title">HRI Scale Reference</div>
  <div class="chart-container">
    <canvas id="hriChart" height="80"></canvas>
  </div>

  <div class="search-row">
    <input class="s-input" id="si" placeholder="Search any city, town, or location worldwide..."
           onkeydown="if(event.key==='Enter')go()">
    <button class="s-btn" onclick="go()">Check Air →</button>
  </div>
</div>

<footer>
  <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank" class="fbadge">
    <span class="dot"></span>
    BXP Protocol — Open Standard for Atmospheric Exposure Data · Apache 2.0
  </a>
</footer>

<script>
{JS_ESC}
const CURRENT_DATA = {export_json};
const CITY_QUERY   = {js_json(raw_query)};
const CITY_LAT     = {_num(data["location"].get("latitude"))};
const CITY_LON     = {_num(data["location"].get("longitude"))};

// ── Map ─────────────────────────────────────────────────────
if (CITY_LAT && CITY_LON) {{
  const map = L.map('city-map', {{
    center: [CITY_LAT, CITY_LON],
    zoom: 10,
    zoomControl: true,
    attributionControl: true,
  }});
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '© OpenStreetMap contributors © CARTO',
    subdomains: 'abcd', maxZoom: 19
  }}).addTo(map);
  const hri = CURRENT_DATA.bxp_hri.score;
  const color = CURRENT_DATA.bxp_hri.color;
  L.circleMarker([CITY_LAT, CITY_LON], {{
    radius: 16, fillColor: color, color: color,
    weight: 2, opacity: 0.9, fillOpacity: 0.4,
  }}).bindPopup(`<b>${{esc(CURRENT_DATA.location.name)}}</b><br>HRI: ${{esc(hri)}} ${{esc(CURRENT_DATA.bxp_hri.level)}}`)
    .addTo(map).openPopup();
}} else {{
  document.getElementById('city-map').innerHTML =
    '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#4a5568">No coordinates available for map</div>';
}}

// ── HRI scale chart ─────────────────────────────────────────
const ctx = document.getElementById('hriChart').getContext('2d');
new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels: ['CLEAN', 'MODERATE', 'ELEVATED', 'HIGH', 'VERY HIGH', 'HAZARDOUS'],
    datasets: [{{
      data: [20, 20, 20, 15, 15, 10],
      backgroundColor: ['#00E676','#FFEB3B','#FF9800','#F44336','#9C27B0','#4A0000'],
      borderWidth: 0,
      borderRadius: 4,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ enabled: false }},
      annotation: {{}}
    }},
    scales: {{
      x: {{
        stacked: true,
        display: false,
        max: 100,
      }},
      y: {{
        ticks: {{
          color: '#4a5568',
          font: {{ family: "'Space Mono', monospace", size: 11 }}
        }},
        grid: {{ display: false }},
        border: {{ display: false }},
      }}
    }},
  }}
}});

// ── Auto-refresh ────────────────────────────────────────────
let refreshTimer = null;
function autoRefresh() {{
  if (refreshTimer) {{
    clearInterval(refreshTimer);
    refreshTimer = null;
    document.getElementById('refresh-btn').textContent = '⟳ Auto-refresh: OFF';
  }} else {{
    refreshTimer = setInterval(refreshCityData, 60000);
    document.getElementById('refresh-btn').textContent = '⟳ Auto-refresh: ON (60s)';
  }}
}}

async function refreshCityData() {{
  try {{
    const r = await fetch('/bxp/v2/city/' + encodeURIComponent(CITY_QUERY));
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('hri-score').textContent = d.bxp_hri.score;
    document.getElementById('hri-level').textContent = d.bxp_hri.level;
    document.getElementById('hri-advice').textContent = d.bxp_hri.advice;
    document.getElementById('ts-label').textContent =
      'Updated ' + d.timestamp.slice(0,19).replace('T',' ') + ' UTC · auto-refreshed';
  }} catch(e) {{}}
}}

// ── Export ──────────────────────────────────────────────────
function exportData() {{
  const blob = new Blob([JSON.stringify(CURRENT_DATA, null, 2)],
    {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = CITY_QUERY.replace(/\\s+/g, '_') + '.bxp.json';
  a.click();
}}

// ── Search ───────────────────────────────────────────────────
function go() {{
  const v = document.getElementById('si').value.trim();
  if (v) window.location.href = '/dashboard/' + encodeURIComponent(v);
}}
</script>
</body>
</html>"""


# ─── Map page ─────────────────────────────────────────────────

MAP_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — Global Air Quality Map</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#060b18;--surface:#0d1628;--border:#1a2540;--text:#e8edf5;--muted:#4a5568;--accent:#00d4ff}
body{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;height:100vh;display:flex;flex-direction:column;}
header{padding:1rem 2rem;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);background:rgba(6,11,24,0.95);z-index:1000;flex-shrink:0;}
.logo{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}
nav a{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}
nav a:hover{color:var(--accent)}
#map{flex:1}
.map-legend{position:absolute;bottom:2rem;right:1rem;z-index:1000;
  background:rgba(6,11,24,0.9);border:1px solid var(--border);
  border-radius:1rem;padding:1rem;font-family:'Space Mono',monospace;font-size:0.65rem;}
.legend-row{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;color:var(--muted)}
.legend-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
.map-status{position:absolute;top:5rem;left:1rem;z-index:1000;
  background:rgba(6,11,24,0.9);border:1px solid var(--border);
  border-radius:0.75rem;padding:0.75rem 1rem;font-family:'Space Mono',monospace;font-size:0.7rem;color:var(--muted)}
</style>
</head>
<body>
<header>
  <span class="logo">BXP GLOBAL MAP</span>
  <nav>
    <a href="/dashboard">🔍 Search</a>
    <a href="/compare">⚖ Compare</a>
    <a href="/">Home</a>
  </nav>
</header>
<div id="map"></div>
<div class="map-status" id="map-status">Loading city data…</div>
<div class="map-legend">
  <div class="legend-row"><div class="legend-dot" style="background:#00E676"></div> CLEAN (0–20)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#FFEB3B"></div> MODERATE (21–40)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#FF9800"></div> ELEVATED (41–60)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#F44336"></div> HIGH (61–75)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#9C27B0"></div> VERY HIGH (76–90)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#4A0000"></div> HAZARDOUS (91+)</div>
</div>
<script>
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const map = L.map('map', {
  center: [20, 10], zoom: 2,
  zoomControl: true,
});
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: 'abcd', maxZoom: 19
}).addTo(map);

async function loadCities() {
  try {
    const r = await fetch('/bxp/v2/readings');
    const d = await r.json();
    const readings = d.data?.readings || [];
    let loaded = 0;
    for (const rec of readings) {
      const lat = rec.location?.latitude;
      const lon = rec.location?.longitude;
      if (!lat || !lon) continue;
      const hri   = rec.bxp_hri?.score ?? 0;
      const level = rec.bxp_hri?.level ?? '';
      const color = rec.bxp_hri?.color ?? '#4a5568';
      const name  = rec.location?.name ?? 'Unknown';
      L.circleMarker([lat, lon], {
        radius: 14 + Math.min(hri / 10, 8),
        fillColor: color, color: color,
        weight: 2, opacity: 0.9, fillOpacity: 0.45,
      }).bindPopup(
        `<b>${esc(name)}</b><br>HRI: ${esc(hri)} <b style="color:${/^#[0-9a-f]{6}$/i.test(color) ? color : '#4a5568'}">${esc(level)}</b>` +
        `<br><a href="/dashboard/${encodeURIComponent(rec.location?.query ?? name)}" ` +
        `style="color:#00d4ff">View dashboard →</a>`
      ).addTo(map);
      loaded++;
    }
    document.getElementById('map-status').textContent =
      loaded + ' locations loaded';
    setTimeout(() => document.getElementById('map-status').style.display='none', 3000);
  } catch(e) {
    document.getElementById('map-status').textContent = 'Error loading data';
  }
}
loadCities();
</script>
</body>
</html>"""


# ─── Compare page ─────────────────────────────────────────────

COMPARE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — Compare Cities</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#060b18;--surface:#0d1628;--border:#1a2540;--text:#e8edf5;--muted:#4a5568;--accent:#00d4ff}
body{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;min-height:100vh;}
header{padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);background:rgba(6,11,24,0.92);
  backdrop-filter:blur(12px);position:sticky;top:0;z-index:100;}
.logo{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}
nav a{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}
nav a:hover{color:var(--accent)}
.main{max-width:1200px;margin:0 auto;padding:3rem 2rem}
h1{font-size:2.5rem;font-weight:800;margin-bottom:0.5rem}
.sub{color:var(--muted);margin-bottom:2.5rem}
.add-row{display:flex;gap:0;background:var(--surface);border:1px solid var(--border);
  border-radius:0.85rem;overflow:hidden;margin-bottom:2rem;transition:border-color 0.2s;max-width:500px}
.add-row:focus-within{border-color:var(--accent)}
.a-input{flex:1;background:transparent;border:none;outline:none;padding:0.85rem 1.25rem;
  color:var(--text);font-family:'Syne',sans-serif;font-size:0.95rem;}
.a-input::placeholder{color:var(--muted)}
.a-btn{background:var(--accent);color:#060b18;border:none;padding:0.85rem 1.5rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.85rem;cursor:pointer;white-space:nowrap;}
.a-btn:hover{opacity:0.85}
.chips{display:flex;flex-wrap:wrap;gap:0.5rem;margin-bottom:2rem}
.chip{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.35rem 0.9rem;
  border:1px solid var(--border);border-radius:999px;color:var(--muted);
  cursor:pointer;background:var(--surface);display:flex;align-items:center;gap:0.5rem;
  transition:all 0.2s}
.chip:hover{border-color:#F44336;color:#F44336}
.chart-wrap{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  padding:2rem;margin-bottom:2rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1rem;margin-bottom:2rem}
.ccard{background:var(--surface);border:1px solid var(--border);border-radius:1rem;padding:1.5rem;
  position:relative;overflow:hidden;transition:transform 0.15s}
.ccard:hover{transform:translateY(-2px)}
.cc-name{font-size:0.8rem;color:var(--muted);margin-bottom:0.5rem;font-weight:700}
.cc-hri{font-size:3rem;font-weight:800;font-family:'Space Mono',monospace;line-height:1}
.cc-level{font-size:0.75rem;font-weight:700;letter-spacing:0.08em;margin-top:0.25rem}
.cc-bar{position:absolute;bottom:0;left:0;height:3px}
.loading{color:var(--muted);font-style:italic;font-size:0.85rem}
</style>
</head>
<body>
<header>
  <span class="logo">BXP COMPARE</span>
  <nav>
    <a href="/dashboard">🔍 Search</a>
    <a href="/map">🗺 Map</a>
    <a href="/">Home</a>
  </nav>
</header>

<div class="main">
  <h1>Compare Cities</h1>
  <p class="sub">Add up to 10 cities to compare air quality side-by-side.</p>

  <div class="add-row">
    <input class="a-input" id="city-input" placeholder="Add a city…"
           onkeydown="if(event.key==='Enter')addCity()">
    <button class="a-btn" onclick="addCity()">Add</button>
  </div>

  <div class="chips" id="chips"></div>

  <div class="chart-wrap" id="chart-wrap" style="display:none">
    <canvas id="compareChart"></canvas>
  </div>

  <div class="cards" id="city-cards"></div>
</div>

<script>
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cities = new Map();
let chart = null;

const DEFAULTS = ['accra','delhi','london','new york','beijing'];
DEFAULTS.forEach(c => loadCity(c));

async function loadCity(name) {
  if (cities.size >= 10) { alert('Maximum 10 cities'); return; }
  const key = name.toLowerCase().trim();
  if (cities.has(key)) return;
  cities.set(key, {name: key, loading: true});
  renderAll();
  try {
    const r = await fetch('/bxp/v2/city/' + encodeURIComponent(key));
    if (!r.ok) { cities.delete(key); renderAll(); return; }
    const d = await r.json();
    cities.set(key, {
      name: d.location?.name ?? key,
      query: key,
      hri:   d.bxp_hri?.score ?? 0,
      level: d.bxp_hri?.level ?? '',
      color: d.bxp_hri?.color ?? '#4a5568',
    });
  } catch(e) {
    cities.delete(key);
  }
  renderAll();
}

function addCity() {
  const v = document.getElementById('city-input').value.trim();
  if (!v) return;
  document.getElementById('city-input').value = '';
  loadCity(v);
}

function removeCity(key) {
  cities.delete(key);
  renderAll();
}

function renderAll() {
  const data = [...cities.values()].filter(c => !c.loading);

  // Chips
  document.getElementById('chips').innerHTML = [...cities.entries()].map(([k, c]) =>
    `<div class="chip" onclick="removeCity(${JSON.stringify(k).replace(/"/g, '&quot;')})">
      ${esc(c.name ?? k)} ${c.loading ? '…' : '✕'}
    </div>`
  ).join('');

  // Cards
  document.getElementById('city-cards').innerHTML = data.map(c =>
    `<div class="ccard">
      <div class="cc-name">${esc(c.name)}</div>
      <div class="cc-hri" style="color:${c.color}">${c.hri}</div>
      <div class="cc-level" style="color:${c.color}">${c.level}</div>
      <div class="cc-bar" style="background:${c.color};width:${c.hri}%"></div>
    </div>`
  ).join('');

  // Chart
  if (data.length === 0) {
    document.getElementById('chart-wrap').style.display = 'none';
    if (chart) { chart.destroy(); chart = null; }
    return;
  }
  document.getElementById('chart-wrap').style.display = 'block';
  const labels = data.map(c => c.name);
  const values = data.map(c => c.hri);
  const colors = data.map(c => c.color);

  if (chart) chart.destroy();
  const ctx = document.getElementById('compareChart').getContext('2d');
  chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors.map(c => c + '80'),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `HRI: ${ctx.raw}`,
          }
        }
      },
      scales: {
        y: {
          min: 0, max: 100,
          ticks: { color: '#4a5568', font: { family: "'Space Mono', monospace" } },
          grid: { color: '#1a2540' },
          border: { display: false },
        },
        x: {
          ticks: { color: '#94a3b8', font: { family: "'Syne', sans-serif", weight: '700' } },
          grid: { display: false },
          border: { display: false },
        }
      }
    }
  });
}
</script>
</body>
</html>"""


# ─── Search page ──────────────────────────────────────────────

SEARCH_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — Global Air Quality</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#060b18;color:#e8edf5;font-family:'Syne',sans-serif;min-height:100vh;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  background-image:radial-gradient(ellipse at 50% 40%,rgba(0,212,255,0.05) 0%,transparent 65%);}
.title{font-size:clamp(2.5rem,7vw,5.5rem);font-weight:800;text-align:center;
  letter-spacing:-0.03em;line-height:0.95;margin-bottom:1.25rem;}
.title span{color:#00d4ff}
.sub{color:#4a5568;text-align:center;margin-bottom:3rem;font-size:1rem;max-width:420px;line-height:1.7}
.wrap{width:100%;max-width:580px;padding:0 1.5rem}
.box{display:flex;background:#0d1628;border:1px solid #1a2540;border-radius:1rem;
  overflow:hidden;transition:border-color 0.2s;}
.box:focus-within{border-color:#00d4ff}
input{flex:1;background:transparent;border:none;outline:none;padding:1.2rem 1.5rem;
  color:#e8edf5;font-family:'Syne',sans-serif;font-size:1.05rem;}
input::placeholder{color:#2d3748}
button{background:#00d4ff;color:#060b18;border:none;padding:1.2rem 2rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.95rem;cursor:pointer;
  transition:background 0.2s;white-space:nowrap;}
button:hover{background:#00b8d9}
.cities{display:flex;flex-wrap:wrap;gap:0.5rem;justify-content:center;
  margin-top:2rem;max-width:580px;padding:0 1.5rem;}
.cp{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.35rem 0.9rem;
  border:1px solid #1a2540;border-radius:999px;color:#4a5568;cursor:pointer;
  transition:all 0.2s;text-decoration:none;}
.cp:hover{border-color:#00d4ff;color:#00d4ff}
.nav-links{display:flex;gap:1.5rem;margin-top:2.5rem;}
.nav-link{font-family:'Space Mono',monospace;font-size:0.7rem;color:#4a5568;
  text-decoration:none;transition:color 0.2s;}
.nav-link:hover{color:#00d4ff}
.foot{position:fixed;bottom:1.5rem;font-family:'Space Mono',monospace;font-size:0.6rem;color:#2d3748;}
.foot a{color:#2d3748;text-decoration:none;transition:color 0.2s}
.foot a:hover{color:#00d4ff}
</style>
</head>
<body>
<div class="title">Air quality<br>for <span>every place</span><br>on earth.</div>
<div class="sub">Real-time atmospheric exposure data. Powered by BXP — the open standard.</div>
<div class="wrap">
  <div class="box">
    <input id="ci" placeholder="Any city, town, village, or location…" autofocus
           onkeydown="if(event.key==='Enter')go()">
    <button onclick="go()">Check Air →</button>
  </div>
</div>
<div class="cities">
  <a class="cp" href="/dashboard/accra">Accra</a>
  <a class="cp" href="/dashboard/lagos">Lagos</a>
  <a class="cp" href="/dashboard/nairobi">Nairobi</a>
  <a class="cp" href="/dashboard/cairo">Cairo</a>
  <a class="cp" href="/dashboard/casablanca">Casablanca</a>
  <a class="cp" href="/dashboard/johannesburg">Johannesburg</a>
  <a class="cp" href="/dashboard/delhi">Delhi</a>
  <a class="cp" href="/dashboard/beijing">Beijing</a>
  <a class="cp" href="/dashboard/jakarta">Jakarta</a>
  <a class="cp" href="/dashboard/tokyo">Tokyo</a>
  <a class="cp" href="/dashboard/mumbai">Mumbai</a>
  <a class="cp" href="/dashboard/dhaka">Dhaka</a>
  <a class="cp" href="/dashboard/karachi">Karachi</a>
  <a class="cp" href="/dashboard/seoul">Seoul</a>
  <a class="cp" href="/dashboard/london">London</a>
  <a class="cp" href="/dashboard/paris">Paris</a>
  <a class="cp" href="/dashboard/berlin">Berlin</a>
  <a class="cp" href="/dashboard/new york">New York</a>
  <a class="cp" href="/dashboard/los angeles">Los Angeles</a>
  <a class="cp" href="/dashboard/sao paulo">São Paulo</a>
  <a class="cp" href="/dashboard/mexico city">Mexico City</a>
  <a class="cp" href="/dashboard/buenos aires">Buenos Aires</a>
  <a class="cp" href="/dashboard/sydney">Sydney</a>
  <a class="cp" href="/dashboard/toronto">Toronto</a>
</div>
<div class="nav-links">
  <a class="nav-link" href="/map">🗺 Global Map</a>
  <a class="nav-link" href="/compare">⚖ Compare Cities</a>
  <a class="nav-link" href="/docs">API Docs</a>
  <a class="nav-link" href="/metrics">Metrics</a>
</div>
<div class="foot">
  <a href="/">BXP Protocol</a> ·
  <a href="/bxp/v2/health">Node Status</a> ·
  <a href="/docs">API</a> ·
  <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a>
</div>
<script>
function go(){
  const v=document.getElementById('ci').value.trim();
  if(v) window.location.href='/dashboard/'+encodeURIComponent(v);
}
</script>
</body>
</html>"""


# ─── Landing page ─────────────────────────────────────────────

LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP Protocol — Open Standard for Atmospheric Exposure Data</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#060b18;--surface:#0d1628;--border:#1a2540;--text:#e8edf5;--muted:#4a5568;--accent:#00d4ff}
body{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;
  background-image:radial-gradient(ellipse at 20% 20%,rgba(0,212,255,0.04) 0%,transparent 60%);}
header{padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);}
.logo{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}
nav a{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}
nav a:hover{color:var(--accent)}
.hero{max-width:900px;margin:5rem auto;padding:0 2rem;text-align:center}
h1{font-size:clamp(2.8rem,7vw,5.5rem);font-weight:800;letter-spacing:-0.03em;line-height:0.95;margin-bottom:1.25rem}
h1 span{color:var(--accent)}
.tag{font-size:1.1rem;color:#94a3b8;max-width:520px;margin:0 auto 2.5rem;line-height:1.7}
.ctas{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:5rem}
.btn-p{background:var(--accent);color:#060b18;padding:0.9rem 2.25rem;border-radius:0.75rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.95rem;text-decoration:none;transition:opacity 0.2s}
.btn-p:hover{opacity:0.85}
.btn-s{background:transparent;color:var(--text);padding:0.9rem 2.25rem;border-radius:0.75rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.95rem;text-decoration:none;
  border:1px solid var(--border);transition:border-color 0.2s}
.btn-s:hover{border-color:var(--accent)}
.stats{display:flex;justify-content:center;gap:4rem;flex-wrap:wrap;padding:2.5rem;
  background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  max-width:750px;margin:0 auto 5rem;}
.sv{font-size:2.5rem;font-weight:800;font-family:'Space Mono',monospace;color:var(--accent);display:block}
.sl{font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;margin-top:0.2rem}
.code{background:var(--surface);border:1px solid var(--border);border-radius:1rem;
  padding:1.5rem 2rem;font-family:'Space Mono',monospace;font-size:0.82rem;
  text-align:left;max-width:560px;margin:0 auto 5rem;line-height:2.1;color:#94a3b8;}
.cm{color:var(--muted)}.cd{color:var(--accent)}
.sec{max-width:900px;margin:0 auto 5rem;padding:0 2rem}
.st{font-size:1.8rem;font-weight:800;margin-bottom:1.75rem;letter-spacing:-0.02em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:1rem;padding:1.5rem}
.ci{font-size:1.4rem;margin-bottom:0.65rem}
.ct{font-weight:700;margin-bottom:0.4rem}
.cb{color:#94a3b8;font-size:0.88rem;line-height:1.6}
footer{border-top:1px solid var(--border);padding:2rem;text-align:center;
  font-family:'Space Mono',monospace;font-size:0.65rem;color:var(--muted);}
footer a{color:var(--muted);text-decoration:none;transition:color 0.2s}
footer a:hover{color:var(--accent)}
.dot{width:7px;height:7px;background:#00E676;border-radius:50%;
  display:inline-block;animation:p 2s infinite;margin-right:0.4rem;vertical-align:middle}
@keyframes p{0%,100%{opacity:1}50%{opacity:0.3}}
</style>
</head>
<body>
<header>
  <span class="logo">BXP PROTOCOL</span>
  <nav>
    <a href="/dashboard">Dashboard</a>
    <a href="/map">Map</a>
    <a href="/compare">Compare</a>
    <a href="/bxp/v2/health">Status</a>
    <a href="/docs">API</a>
    <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a>
  </nav>
</header>

<div class="hero">
  <h1>The open standard<br>for <span>air quality</span><br>data.</h1>
  <p class="tag">Like HTTP for the web — any device writes it, any software reads it, nobody owns it. Apache 2.0. Forever free.</p>
  <div class="ctas">
    <a href="/dashboard" class="btn-p">Live Global Dashboard →</a>
    <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank" class="btn-s">View Specification</a>
  </div>
  <div class="stats">
    <div><span class="sv">7M</span><span class="sl">Deaths per year</span></div>
    <div><span class="sv">31</span><span class="sl">Atmospheric agents</span></div>
    <div><span class="sv">∞</span><span class="sl">Cities worldwide</span></div>
  </div>
  <div class="code">
    <span class="cm"># Run your own BXP node in 3 minutes</span><br>
    <span class="cd">git clone</span> https://github.com/bxpprotocol/bxp-spec<br>
    <span class="cd">cd</span> bxp-spec/reference-server<br>
    <span class="cd">pip install</span> -r requirements.txt<br>
    <span class="cd">python</span> server.py
  </div>
</div>

<div class="sec">
  <div class="st">What BXP defines</div>
  <div class="grid">
    <div class="card"><div class="ci">📄</div><div class="ct">Universal File Format</div>
      <div class="cb">A .bxp file any device or software can read and write. One format. Every sensor. Everywhere.</div></div>
    <div class="card"><div class="ci">📊</div><div class="ct">BXP_HRI Score</div>
      <div class="cb">Composite Health Risk Index with WHO-derived weighting across all atmospheric agents. 0–100.</div></div>
    <div class="card"><div class="ci">🌐</div><div class="ct">REST API Spec</div>
      <div class="cb">Federated node architecture. Any institution runs a node. Nodes interoperate. Nobody owns the network.</div></div>
    <div class="card"><div class="ci">🔒</div><div class="ct">Privacy Framework</div>
      <div class="cb">Individual records protected by design. Geohash-5 floor. k≥5 anonymity. Cryptographic deletion.</div></div>
    <div class="card"><div class="ci">🗺</div><div class="ct">Global Map</div>
      <div class="cb">Real-time air quality plotted worldwide. Click any marker to see the full city dashboard.</div></div>
    <div class="card"><div class="ci">⚖</div><div class="ct">City Comparison</div>
      <div class="cb">Side-by-side HRI comparison for up to 10 cities. Ideal for researchers and health professionals.</div></div>
  </div>
</div>

<div class="sec" style="text-align:center">
  <div class="st">Live public node</div>
  <p style="color:#94a3b8;margin-bottom:2rem"><span class="dot"></span>Operational — real-time global data</p>
  <a href="/dashboard" class="btn-p">Open Global Dashboard →</a>
</div>

<footer>
  BXP Protocol · Apache 2.0 ·
  <a href="https://doi.org/10.5281/zenodo.18906812" target="_blank">DOI 10.5281/zenodo.18906812</a> ·
  <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a> ·
  <a href="mailto:bxpprotocol@proton.me">Contact</a>
</footer>
</body>
</html>"""




# ─── Small standalone pages (widget / not-found) ──────────────

def not_found_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html><body style="background:#060b18;color:white;font-family:sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;
margin:0;flex-direction:column;gap:1rem">
<h1 style="font-size:2rem">Location not found</h1>
<p style="color:#4a5568;max-width:400px;text-align:center">{esc(message)}</p>
<a href="/dashboard" style="color:#00d4ff;text-decoration:none">← Search another location</a>
</body></html>"""


def widget_missing_page(city: str) -> str:
    return (
        '<html><body style="background:#060b18;color:#4a5568;font-family:sans-serif;'
        'display:flex;align-items:center;justify-content:center;height:100%;margin:0">'
        f'No data for "{esc(city)}"</body></html>'
    )


def widget_page(data: dict, city: str) -> str:
    color = str(data["bxp_hri"]["color"])
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = "#00d4ff"
    hri, level = esc(data["bxp_hri"]["score"]), esc(data["bxp_hri"]["level"])
    advice, loc = esc(data["bxp_hri"]["advice"]), esc(data["location"]["name"])
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#060b18;color:#e8edf5;font-family:'Segoe UI',sans-serif;
  padding:12px;height:100%;display:flex;flex-direction:column;gap:8px}}
.loc{{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;color:#94a3b8}}
.score{{font-size:42px;font-weight:800;color:{color};line-height:1;
  font-variant-numeric:tabular-nums}}
.level{{font-size:11px;font-weight:700;color:{color};letter-spacing:.1em}}
.advice{{font-size:10px;color:#4a5568;line-height:1.4;flex:1}}
.brand{{font-size:9px;color:#1a2540;text-align:right;margin-top:auto}}
.brand a{{color:#1a2540;text-decoration:none}}
</style></head>
<body>
<div class="loc">{loc}</div>
<div class="score">{hri}</div>
<div class="level">{level}</div>
<div class="advice">{advice}</div>
<div class="brand"><a href="/dashboard/{quote(city, safe='')}" target="_blank" rel="noopener">BXP Protocol</a></div>
</body></html>"""
