"""
BXP Protocol Reference Node v2.1
Real-time global atmospheric exposure data
Powered by AQICN + BXP standard format
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx
import asyncio
import json
import time
import hashlib
from datetime import datetime, timezone
import uvicorn

# ─────────────────────────────────────────
AQICN_TOKEN = "68fc34ffbfaf451cc4250b87158ffe04a3dc5dfd"
BXP_VERSION = "2.0"
NODE_ID = "bxp-public-node-001"
# ─────────────────────────────────────────

app = FastAPI(
    title="BXP Protocol Node",
    description="Open standard for atmospheric exposure data",
    version="2.1.0",
    docs_url="/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache
cache = {}
cache_timestamps = {}
CACHE_TTL = 600  # 10 minutes

WHO_THRESHOLDS = {
    "pm25": 15.0, "pm10": 45.0, "no2": 25.0,
    "o3": 100.0, "co": 4.0, "so2": 40.0
}

WEIGHTS = {
    "pm25": 0.35, "pm10": 0.15, "no2": 0.15,
    "o3": 0.12, "co": 0.10, "so2": 0.05
}

def calculate_hri(readings: dict) -> float:
    score = 0.0
    for agent, weight in WEIGHTS.items():
        val = readings.get(agent)
        thresh = WHO_THRESHOLDS.get(agent)
        if val is not None and thresh:
            normalized = min(float(val) / thresh, 1.0)
            score += normalized * weight
    return round(score * 100, 1)

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
    advice = {
        "CLEAN": "Air quality is excellent. Enjoy outdoor activities freely.",
        "MODERATE": "Air quality is acceptable. Sensitive individuals should limit prolonged outdoor exertion.",
        "ELEVATED": "Sensitive groups should reduce prolonged outdoor exertion.",
        "HIGH": "Everyone should reduce prolonged outdoor exertion. Sensitive groups stay indoors.",
        "VERY_HIGH": "Avoid outdoor activities. Sensitive groups must stay indoors.",
        "HAZARDOUS": "Health emergency. Everyone should avoid all outdoor activity."
    }
    return advice.get(level, "")

async def fetch_city_data(city: str) -> Optional[dict]:
    cache_key = city.lower().strip()
    now = time.time()

    if cache_key in cache and (now - cache_timestamps.get(cache_key, 0)) < CACHE_TTL:
        return cache[cache_key]

    url = f"https://api.waqi.info/feed/{city}/?token={AQICN_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            data = resp.json()

        if data.get("status") != "ok":
            return None

        d = data["data"]
        iaqi = d.get("iaqi", {})

        readings = {
            "pm25": iaqi.get("pm25", {}).get("v"),
            "pm10": iaqi.get("pm10", {}).get("v"),
            "no2":  iaqi.get("no2",  {}).get("v"),
            "o3":   iaqi.get("o3",   {}).get("v"),
            "co":   iaqi.get("co",   {}).get("v"),
            "so2":  iaqi.get("so2",  {}).get("v"),
        }

        hri = calculate_hri(readings)
        level = hri_level(hri)

        city_name = d.get("city", {}).get("name", city)
        geo = d.get("city", {}).get("geo", [0, 0])

        bxp_record = {
            "bxp_version": BXP_VERSION,
            "record_id": hashlib.sha256(f"{city_name}{time.time()}".encode()).hexdigest()[:16],
            "node_id": NODE_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {
                "name": city_name,
                "query": city,
                "latitude": geo[0] if len(geo) > 0 else None,
                "longitude": geo[1] if len(geo) > 1 else None,
            },
            "readings": {k: v for k, v in readings.items() if v is not None},
            "bxp_hri": {
                "score": hri,
                "level": level,
                "color": hri_color(hri),
                "advice": hri_advice(level),
            },
            "source": "AQICN",
            "aqi": d.get("aqi"),
            "dominant_pollutant": d.get("dominentpol"),
            "attribution": d.get("attributions", [{}])[0].get("name", "AQICN") if d.get("attributions") else "AQICN",
        }

        cache[cache_key] = bxp_record
        cache_timestamps[cache_key] = now
        return bxp_record

    except Exception:
        return None


# ─── ROUTES ───────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(LANDING_PAGE)

@app.get("/bxp/v2/health")
async def health():
    return {
        "status": "operational",
        "node_id": NODE_ID,
        "bxp_version": BXP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cached_locations": len(cache),
        "spec": "https://github.com/bxpprotocol/bxp-spec",
        "doi": "https://doi.org/10.5281/zenodo.18906812"
    }

@app.get("/bxp/v2/readings/{city}")
async def get_city(city: str):
    data = await fetch_city_data(city)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data found for '{city}'. Try a different city name.")
    return data

@app.get("/bxp/v2/readings")
async def get_default_readings():
    cities = ["accra", "lagos", "delhi", "beijing", "london",
              "sao paulo", "new york", "nairobi", "jakarta", "cairo"]
    results = []
    for city in cities:
        data = await fetch_city_data(city)
        if data:
            results.append(data)
    return {"count": len(results), "readings": results}

@app.get("/dashboard/{city}", response_class=HTMLResponse)
async def dashboard(city: str):
    data = await fetch_city_data(city)
    if not data:
        return HTMLResponse(f"""<!DOCTYPE html>
<html><body style="background:#060b18;color:white;font-family:sans-serif;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column;gap:1rem">
<h1 style="font-size:2rem">Location not found</h1>
<p style="color:#4a5568">No air quality data available for "{city}"</p>
<a href="/dashboard" style="color:#00d4ff;text-decoration:none">← Try another location</a>
</body></html>""")
    return HTMLResponse(render_dashboard(data))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_home():
    return HTMLResponse(SEARCH_PAGE)


# ─── DASHBOARD RENDERER ───────────────────

def render_dashboard(data: dict) -> str:
    hri = data["bxp_hri"]["score"]
    level = data["bxp_hri"]["level"]
    color = data["bxp_hri"]["color"]
    advice = data["bxp_hri"]["advice"]
    location = data["location"]["name"]
    readings = data["readings"]
    timestamp = data["timestamp"]
    aqi = data.get("aqi", "N/A")
    dominant = (data.get("dominant_pollutant") or "").upper()
    query = data["location"]["query"]

    # parse color to rgb for glow
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        rgb = f"{r},{g},{b}"
    except Exception:
        rgb = "0,212,255"

    def reading_card(label, key, unit):
        val = readings.get(key)
        if val is None:
            return f'''<div class="r-card">
<span class="r-label">{label}</span>
<span class="r-val na">N/A</span>
<div class="r-bar-bg"><div class="r-bar" style="width:0%"></div></div>
<span class="r-who">WHO: {WHO_THRESHOLDS.get(key,"—")} {unit}</span>
</div>'''
        thresh = WHO_THRESHOLDS.get(key, 100)
        pct = min(int((float(val) / thresh) * 100), 100)
        bar_color = "#00E676" if pct < 50 else "#FF9800" if pct < 100 else "#F44336"
        return f'''<div class="r-card">
<span class="r-label">{label}</span>
<span class="r-val">{val}<span class="r-unit"> {unit}</span></span>
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

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — {location} Air Quality</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#060b18;--surface:#0d1628;--border:#1a2540;
  --text:#e8edf5;--muted:#4a5568;--accent:#00d4ff;
  --hri:{color};--rgb:{rgb};
}}
body{{
  background:var(--bg);color:var(--text);
  font-family:'Syne',sans-serif;min-height:100vh;
  background-image:
    radial-gradient(ellipse at 15% 15%,rgba(0,212,255,0.03) 0%,transparent 50%),
    radial-gradient(ellipse at 85% 85%,rgba(var(--rgb),0.06) 0%,transparent 50%);
}}
header{{
  padding:1.25rem 2rem;display:flex;align-items:center;
  justify-content:space-between;border-bottom:1px solid var(--border);
  background:rgba(6,11,24,0.92);backdrop-filter:blur(12px);
  position:sticky;top:0;z-index:100;
}}
.logo{{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}}
nav a{{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}}
nav a:hover{{color:var(--accent)}}
.main{{max-width:1100px;margin:0 auto;padding:3rem 2rem}}
.loc{{font-size:clamp(2rem,5vw,3.5rem);font-weight:800;letter-spacing:-0.02em;line-height:1;margin-bottom:0.4rem}}
.ts{{font-family:'Space Mono',monospace;font-size:0.7rem;color:var(--muted);margin-bottom:2.5rem}}
.hri-block{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:1.5rem;padding:2.5rem;margin-bottom:2rem;
  display:grid;grid-template-columns:auto 1fr;gap:3rem;
  align-items:center;position:relative;overflow:hidden;
}}
.hri-block::after{{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--hri);
}}
.score{{
  font-size:clamp(4rem,10vw,6.5rem);font-weight:800;
  font-family:'Space Mono',monospace;color:var(--hri);line-height:1;
  text-shadow:0 0 60px rgba(var(--rgb),0.4);
}}
.level{{font-size:1.4rem;font-weight:700;color:var(--hri);margin-bottom:0.6rem;letter-spacing:0.05em}}
.advice{{font-size:0.95rem;color:#94a3b8;line-height:1.65;margin-bottom:1rem;max-width:480px}}
.pills{{display:flex;gap:0.75rem;flex-wrap:wrap}}
.meta-pill{{
  font-family:'Space Mono',monospace;font-size:0.65rem;
  padding:0.3rem 0.8rem;border:1px solid var(--border);
  border-radius:999px;color:var(--muted);
}}
.grid{{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));
  gap:0.85rem;margin-bottom:2.5rem;
}}
.r-card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:1rem;padding:1.4rem;
  transition:border-color 0.2s,transform 0.15s;
}}
.r-card:hover{{border-color:var(--accent);transform:translateY(-2px)}}
.r-label{{font-family:'Space Mono',monospace;font-size:0.65rem;color:var(--muted);
  letter-spacing:0.12em;text-transform:uppercase;display:block;margin-bottom:0.5rem}}
.r-val{{font-size:1.9rem;font-weight:800;font-family:'Space Mono',monospace;
  display:block;margin-bottom:0.65rem}}
.r-val.na{{color:var(--muted);font-size:1.4rem}}
.r-unit{{font-size:0.85rem;color:var(--muted);font-weight:400}}
.r-bar-bg{{height:3px;background:var(--border);border-radius:999px;margin-bottom:0.5rem}}
.r-bar{{height:3px;border-radius:999px}}
.r-who{{font-family:'Space Mono',monospace;font-size:0.6rem;color:var(--muted)}}
.search-row{{
  display:flex;gap:0;background:var(--surface);
  border:1px solid var(--border);border-radius:0.85rem;
  overflow:hidden;margin-bottom:3rem;
  transition:border-color 0.2s;
}}
.search-row:focus-within{{border-color:var(--accent)}}
.s-input{{
  flex:1;background:transparent;border:none;outline:none;
  padding:1rem 1.25rem;color:var(--text);
  font-family:'Syne',sans-serif;font-size:1rem;
}}
.s-input::placeholder{{color:var(--muted)}}
.s-btn{{
  background:var(--accent);color:#060b18;border:none;
  padding:1rem 1.75rem;font-family:'Syne',sans-serif;
  font-weight:700;font-size:0.9rem;cursor:pointer;
  transition:opacity 0.2s;white-space:nowrap;
}}
.s-btn:hover{{opacity:0.85}}
footer{{
  border-top:1px solid var(--border);padding:1.5rem 2rem;
  text-align:center;max-width:1100px;margin:0 auto;
}}
.fbadge{{
  display:inline-flex;align-items:center;gap:0.5rem;
  font-family:'Space Mono',monospace;font-size:0.65rem;
  color:var(--muted);text-decoration:none;
  border:1px solid var(--border);padding:0.4rem 1rem;
  border-radius:999px;transition:all 0.2s;
}}
.fbadge:hover{{border-color:var(--accent);color:var(--accent)}}
.dot{{width:6px;height:6px;background:#00E676;border-radius:50%;
  animation:pulse 2s infinite}}
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
    <a href="/bxp/v2/readings/{query}">JSON</a>
    <a href="/bxp/v2/health">Status</a>
    <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a>
  </nav>
</header>

<div class="main">
  <div class="loc">{location}</div>
  <div class="ts">Updated {timestamp[:19].replace("T"," ")} UTC · BXP v{BXP_VERSION} · {data.get("attribution","AQICN")}</div>

  <div class="hri-block">
    <div class="score">{hri}</div>
    <div>
      <div class="level">{level}</div>
      <div class="advice">{advice}</div>
      <div class="pills">
        <span class="meta-pill">AQI {aqi}</span>
        {dominant_pill}
        <span class="meta-pill">BXP_HRI {hri}/100</span>
      </div>
    </div>
  </div>

  <div class="grid">{cards}</div>

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
function go(){{
  const v=document.getElementById('si').value.trim();
  if(v) window.location.href='/dashboard/'+encodeURIComponent(v);
}}
</script>
</body>
</html>"""


# ─── SEARCH PAGE ──────────────────────────

SEARCH_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — Global Air Quality</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  background:#060b18;color:#e8edf5;font-family:'Syne',sans-serif;
  min-height:100vh;display:flex;flex-direction:column;
  align-items:center;justify-content:center;
  background-image:radial-gradient(ellipse at 50% 40%,rgba(0,212,255,0.05) 0%,transparent 65%);
}
.title{
  font-size:clamp(2.5rem,7vw,5.5rem);font-weight:800;
  text-align:center;letter-spacing:-0.03em;line-height:0.95;margin-bottom:1.25rem;
}
.title span{color:#00d4ff}
.sub{color:#4a5568;text-align:center;margin-bottom:3rem;font-size:1rem;
  max-width:420px;line-height:1.7}
.wrap{width:100%;max-width:580px;padding:0 1.5rem}
.box{
  display:flex;background:#0d1628;border:1px solid #1a2540;
  border-radius:1rem;overflow:hidden;transition:border-color 0.2s;
}
.box:focus-within{border-color:#00d4ff}
input{
  flex:1;background:transparent;border:none;outline:none;
  padding:1.2rem 1.5rem;color:#e8edf5;
  font-family:'Syne',sans-serif;font-size:1.05rem;
}
input::placeholder{color:#2d3748}
button{
  background:#00d4ff;color:#060b18;border:none;
  padding:1.2rem 2rem;font-family:'Syne',sans-serif;
  font-weight:700;font-size:0.95rem;cursor:pointer;
  transition:background 0.2s;white-space:nowrap;
}
button:hover{background:#00b8d9}
.cities{
  display:flex;flex-wrap:wrap;gap:0.5rem;
  justify-content:center;margin-top:2rem;
  max-width:580px;padding:0 1.5rem;
}
.cp{
  font-family:'Space Mono',monospace;font-size:0.65rem;
  padding:0.35rem 0.9rem;border:1px solid #1a2540;
  border-radius:999px;color:#4a5568;cursor:pointer;
  transition:all 0.2s;text-decoration:none;
}
.cp:hover{border-color:#00d4ff;color:#00d4ff}
.foot{
  position:fixed;bottom:1.5rem;
  font-family:'Space Mono',monospace;font-size:0.6rem;color:#2d3748;
}
.foot a{color:#2d3748;text-decoration:none;transition:color 0.2s}
.foot a:hover{color:#00d4ff}
</style>
</head>
<body>
<div class="title">Air quality<br>for <span>every place</span><br>on earth.</div>
<div class="sub">Real-time atmospheric exposure data. Powered by BXP — the open standard.</div>
<div class="wrap">
  <div class="box">
    <input id="ci" placeholder="Any city, town, village, or location..." autofocus
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
<div class="foot">
  <a href="/" >BXP Protocol</a> ·
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


# ─── LANDING PAGE ─────────────────────────

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
body{
  background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;
  background-image:radial-gradient(ellipse at 20% 20%,rgba(0,212,255,0.04) 0%,transparent 60%);
}
header{
  padding:1.25rem 2rem;display:flex;align-items:center;
  justify-content:space-between;border-bottom:1px solid var(--border);
}
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
.stats{
  display:flex;justify-content:center;gap:4rem;flex-wrap:wrap;
  padding:2.5rem;background:var(--surface);border:1px solid var(--border);
  border-radius:1.5rem;max-width:750px;margin:0 auto 5rem;
}
.sv{font-size:2.5rem;font-weight:800;font-family:'Space Mono',monospace;color:var(--accent);display:block}
.sl{font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;margin-top:0.2rem}
.code{
  background:var(--surface);border:1px solid var(--border);border-radius:1rem;
  padding:1.5rem 2rem;font-family:'Space Mono',monospace;font-size:0.82rem;
  text-align:left;max-width:560px;margin:0 auto 5rem;line-height:2.1;color:#94a3b8;
}
.cm{color:var(--muted)}.cd{color:var(--accent)}
.sec{max-width:900px;margin:0 auto 5rem;padding:0 2rem}
.st{font-size:1.8rem;font-weight:800;margin-bottom:1.75rem;letter-spacing:-0.02em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:1rem;padding:1.5rem}
.ci{font-size:1.4rem;margin-bottom:0.65rem}
.ct{font-weight:700;margin-bottom:0.4rem}
.cb{color:#94a3b8;font-size:0.88rem;line-height:1.6}
footer{
  border-top:1px solid var(--border);padding:2rem;text-align:center;
  font-family:'Space Mono',monospace;font-size:0.65rem;color:var(--muted);
}
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
    <span class="cd">pip install</span> fastapi uvicorn pydantic httpx<br>
    <span class="cd">python</span> server.py
  </div>
</div>

<div class="sec">
  <div class="st">What BXP defines</div>
  <div class="grid">
    <div class="card"><div class="ci">📄</div><div class="ct">Universal File Format</div><div class="cb">A .bxp file any device or software can read and write. One format. Every sensor. Everywhere.</div></div>
    <div class="card"><div class="ci">📊</div><div class="ct">BXP_HRI Score</div><div class="cb">Composite Health Risk Index with WHO-derived weighting across all atmospheric agents. 0–100.</div></div>
    <div class="card"><div class="ci">🌐</div><div class="ct">REST API Spec</div><div class="cb">Federated node architecture. Any institution runs a node. Nodes interoperate. Nobody owns the network.</div></div>
    <div class="card"><div class="ci">🔒</div><div class="ct">Privacy Framework</div><div class="cb">Individual records protected by design. Only aggregates shared across the federated network.</div></div>
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


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
