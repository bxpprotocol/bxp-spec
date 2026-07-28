#!/usr/bin/env python3
"""
BXP Command Line Tool v2.1
Breathe Exposure Protocol

Usage:
    bxp generate --pm25 47.2 --lat 5.6037 --lon -0.1870
    bxp read reading.bxp.json
    bxp validate reading.bxp.json
    bxp submit --file reading.bxp.json
    bxp batch-submit --dir ./readings/
    bxp export reading.bxp.json --format csv
    bxp hri --pm25 67.0 --no2 31.0 --duration 8h --population sensitive
    bxp server-status
    bxp map ./readings/ --output map.html
    bxp config set server http://localhost:5000
    bxp config show

Env vars:
    BXP_SERVER_URL    Default server URL (overrides config file)
    BXP_DEVICE_TOKEN  Default device token

Config file: ~/.bxp/config.json
"""

import sys
import json
import argparse
import os
import csv
import io
from pathlib import Path
from datetime import datetime, timezone

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent / "sdk" / "python"))
from bxp_sdk import (
    write_bxp, read_bxp, validate_bxp, calculate_risk,
    encode_geohash, BXPClient, BXP_VERSION, RISK_LEVELS,
    WHO_THRESHOLDS, HRI_WEIGHTS,
)

# ─── Config file ─────────────────────────────────────────────────

CONFIG_PATH = Path("~/.bxp/config.json").expanduser()


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2), encoding="utf-8"
    )


def get_server_url(args_server: str = None) -> str:
    """Resolve server URL: CLI arg → env var → config → default."""
    if args_server:
        return args_server
    env = os.environ.get("BXP_SERVER_URL")
    if env:
        return env
    cfg = load_config()
    return cfg.get("server", "http://localhost:5000")


def get_device_token(args_token: str = None) -> str:
    """Resolve device token: CLI arg → env var → config."""
    if args_token:
        return args_token
    env = os.environ.get("BXP_DEVICE_TOKEN")
    if env:
        return env
    cfg = load_config()
    return cfg.get("token", "")


# ─── Color output ─────────────────────────────────────────────────

COLORS = {
    "reset":   "\033[0m",  "bold":    "\033[1m",
    "green":   "\033[92m", "yellow":  "\033[93m",
    "red":     "\033[91m", "blue":    "\033[94m",
    "cyan":    "\033[96m", "magenta": "\033[95m",
    "gray":    "\033[90m", "white":   "\033[97m",
}
LEVEL_COLORS = {
    "CLEAN":     "green",  "MODERATE":  "yellow",
    "ELEVATED":  "yellow", "HIGH":      "red",
    "VERY_HIGH": "red",    "HAZARDOUS": "magenta",
}


def c(text: str, color: str) -> str:
    if sys.stdout.isatty():
        return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"
    return text


def bold(text: str) -> str:
    return c(text, "bold")


def print_sep():
    print(c("─" * 60, "gray"))


def print_hri_banner(score, level, advice):
    lc = LEVEL_COLORS.get(level, "white")
    print()
    print_sep()
    print(f"  {bold('BXP Health Risk Index')}  "
          f"{c(str(score), lc)}  {c(f'[{level}]', lc)}")
    print(f"  {c(advice, 'gray')}")
    print_sep()
    print()


# ─── Commands ─────────────────────────────────────────────────────

def cmd_generate(args):
    output = args.output or f"reading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bxp.json"
    data = {}
    if args.lat:  data["latitude"]  = float(args.lat)
    if args.lon:  data["longitude"] = float(args.lon)
    if args.gh:   data["geohash"]   = args.gh

    agent_map = {
        "pm25": "pm25",   "pm10": "pm10",  "no2": "no2",
        "o3": "o3",       "co": "co",      "so2": "so2",
        "tvoc": "tvoc",   "benz": "benz",  "form": "form",
        "temp": "temp",   "rh": "humidity","press": "pressure",
        "uv": "uv",       "co2": "co2",    "pm1": "pm1",
    }
    for arg_key, data_key in agent_map.items():
        val = getattr(args, arg_key, None)
        if val is not None:
            data[data_key] = float(val)

    if args.indoor:
        data["indoorOutdoor"] = "indoor"
    if args.location:
        data["context"] = {"location": args.location}

    if not data:
        print(c("Error: No measurement values provided.", "red"))
        print("Example: bxp generate --pm25 47.2 --lat 5.6037 --lon -0.1870")
        sys.exit(1)

    try:
        record = write_bxp(output, data, device_uuid=args.device_uuid)
        print()
        print(bold(f"  BXP file generated: {c(output, 'cyan')}"))
        print_sep()
        if record.get("geohash"):
            print(f"  Geohash:   {c(record['geohash'], 'cyan')}")
        if record.get("latitude") is not None:
            print(f"  Location:  {record['latitude']}, {record['longitude']}")

        for a in record.get("agents", []):
            thr = WHO_THRESHOLDS.get(a["agentId"])
            who = ""
            if thr:
                if float(a["value"]) > thr:
                    who = c(f"  ↑ EXCEEDS WHO ({thr})", "red")
                else:
                    who = c(f"  ✓ within WHO ({thr})", "green")
            print(f"  {c('  ' + a['agentId'], 'gray')}: {a['value']} {a['unit']}{who}")

        hri = record.get("bxpHri", 0)
        level = record.get("bxpHriLevel", "CLEAN")
        advice = next((la for lo, hi, ln, lc, la, _ in RISK_LEVELS
                       if lo <= hri <= hi), "")
        print_hri_banner(hri, level, advice)

        if args.verbose:
            print(c("  Full record:", "gray"))
            print(json.dumps(record, indent=2, default=str))

    except Exception as e:
        print(c(f"Error: {e}", "red"))
        sys.exit(1)


def cmd_read(args):
    path = args.file
    if not Path(path).exists():
        print(c(f"Error: File not found: {path}", "red"))
        sys.exit(1)

    record = read_bxp(path)
    print()
    print(bold(f"  BXP Record: {c(path, 'cyan')}"))
    print_sep()
    print(f"  BXP Version: {record.get('bxpVersion', '?')}")
    print(f"  Device UUID: {c(record.get('deviceUuid', '?'), 'gray')}")
    print(f"  Geohash:     {c(record.get('geohash', '?'), 'cyan')}")

    ts = record.get("timestampUs")
    if ts:
        dt = datetime.fromtimestamp(ts / 1_000_000, tz=timezone.utc)
        print(f"  Timestamp:   {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    if record.get("latitude") is not None:
        print(f"  Location:    {record['latitude']}, {record['longitude']}")

    quality = record.get("quality", {})
    qflag = quality.get("flag", "?")
    qcol  = "green" if qflag == "VALIDATED" else (
            "yellow" if qflag == "UNVALIDATED" else "red")
    print(f"  Quality:     {c(qflag, qcol)} "
          f"({quality.get('confidence', 0) * 100:.0f}% confidence)")

    if record.get("_integrityOk") is True:
        print(f"  Integrity:   {c('✓ Hash verified', 'green')}")
    elif record.get("_integrityOk") is False:
        print(f"  Integrity:   {c('✗ Hash mismatch', 'red')}")

    print_sep()
    print(f"  {'Agent':<10} {'Value':<12} {'Unit':<10} {'WHO Limit':<12} Status")
    print_sep()
    for a in record.get("agents", []):
        aid  = a.get("agentId", "?")
        val  = a.get("value", 0)
        unit = a.get("unit", "")
        thr  = WHO_THRESHOLDS.get(aid)
        thr_s = str(thr) if thr else "—"
        stat  = (c("↑ EXCEEDS", "red") if thr and float(val) > thr
                 else (c("✓ OK", "green") if thr else c("—", "gray")))
        print(f"  {aid:<10} {str(val):<12} {unit:<10} {thr_s:<12} {stat}")

    hri   = record.get("bxpHri", 0)
    level = record.get("bxpHriLevel", "")
    advice = next((la for lo, hi, ln, lc, la, _ in RISK_LEVELS
                   if lo <= hri <= hi), "")
    print_hri_banner(hri, level, advice)

    if args.raw:
        print(c("  Raw JSON:", "gray"))
        print(json.dumps(
            {k: v for k, v in record.items() if not k.startswith("_")},
            indent=2, default=str
        ))


def cmd_validate(args):
    path = args.file
    if not Path(path).exists():
        print(c(f"Error: File not found: {path}", "red"))
        sys.exit(1)

    result = validate_bxp(path)
    print()
    print(bold(f"  BXP Validation: {c(path, 'cyan')}"))
    print_sep()
    print(f"  Result:  {c('✓ VALID', 'green') if result['valid'] else c('✗ INVALID', 'red')}")
    print(f"  Summary: {result['summary']}")

    for e in result.get("errors", []):
        print(f"    {c('✗', 'red')} {e}")
    for w in result.get("warnings", []):
        print(f"    {c('⚠', 'yellow')} {w}")

    if result["valid"] and not result["warnings"]:
        print(f"\n  {c('All checks passed.', 'green')}")
    print()
    sys.exit(0 if result["valid"] else 1)


def cmd_hri(args):
    kwargs = {}
    for key in ["pm25","pm10","no2","o3","co","so2","tvoc"]:
        val = getattr(args, key, None)
        if val is not None:
            kwargs[key] = float(val)

    if not kwargs:
        print(c("Error: Provide at least one measurement value.", "red"))
        sys.exit(1)

    result = calculate_risk(**kwargs,
                            duration=args.duration or "1h",
                            population=args.population or "general")
    print()
    print(bold("  BXP Health Risk Index Calculator"))
    print_sep()
    lc = LEVEL_COLORS.get(result['level'], 'white')
    print(f"  Score:      {c(str(result['score']), lc)}")
    print(f"  Level:      {c(result['level'], lc)}")
    print(f"  Duration:   {result['duration']}")
    print(f"  Population: {result['population']}")
    print(f"  Advice:     {result['advice']}")
    print(f"  Sensitive:  {result['sensitiveAdvice']}")

    if result["breakdown"]:
        print()
        print_sep()
        print(f"  {'Agent':<10} {'Value':<10} {'Risk':<8} {'Weight':<8} Contrib")
        print_sep()
        for aid, b in result["breakdown"].items():
            over = c(" ↑ WHO", "red") if b["exceedsWho"] else ""
            print(f"  {aid:<10} {str(b['value']):<10} "
                  f"{b['normalizedRisk']:<8} "
                  f"{HRI_WEIGHTS.get(aid,0):<8} "
                  f"{b['contribution']}{over}")
    print()


def cmd_submit(args):
    server = get_server_url(getattr(args, "server", None))
    token  = get_device_token(getattr(args, "token", None))
    client = BXPClient(server, device_token=token or None)

    print(c("  Checking server…", "gray"))
    health = client.health()
    if health.get("status") != "ok":
        print(c(f"  Server unreachable: {server}", "red"))
        sys.exit(1)
    print(c(f"  Online: BXP v{health.get('data',{}).get('bxpVersion','?')}", "green"))

    if not args.file:
        print(c("  Error: --file required", "red"))
        sys.exit(1)

    record  = read_bxp(args.file)
    lat     = record.get("latitude")
    lon     = record.get("longitude")
    agents  = record.get("agents", [])

    if lat is None or lon is None:
        print(c("  Error: File has no coordinates", "red"))
        sys.exit(1)

    result = client.submit(latitude=lat, longitude=lon, agents=agents)
    if result.get("success"):
        print()
        print(bold("  Submission successful"))
        print_sep()
        print(f"  Reading ID: {c(result['readingId'], 'cyan')}")
        print(f"  Geohash:    {result.get('geohash')}")
        print(f"  BXP_HRI:    {c(str(result['bxpHri']), 'yellow')} [{result['level']}]")
        print(f"  Quality:    {result['qualityFlag']}")
        print()
    else:
        print(c(f"  Failed: {result.get('error')}", "red"))
        sys.exit(1)


def cmd_batch_submit(args):
    """Submit all .bxp.json files in a directory."""
    server = get_server_url(getattr(args, "server", None))
    token  = get_device_token(getattr(args, "token", None))
    client = BXPClient(server, device_token=token or None)

    directory = Path(args.dir)
    if not directory.is_dir():
        print(c(f"Error: Not a directory: {args.dir}", "red"))
        sys.exit(1)

    files = list(directory.glob("*.bxp.json")) + list(directory.glob("*.bxp.json.json"))
    if not files:
        print(c(f"No .bxp.json files found in {args.dir}", "yellow"))
        sys.exit(0)

    print()
    print(bold(f"  Batch submit: {len(files)} file(s) → {server}"))
    print_sep()

    ok = fail = 0
    for f in sorted(files):
        try:
            record = read_bxp(f)
            lat    = record.get("latitude")
            lon    = record.get("longitude")
            agents = record.get("agents", [])
            if lat is None or lon is None:
                print(f"  {c('SKIP', 'gray')} {f.name} — no coordinates")
                fail += 1
                continue
            result = client.submit(latitude=lat, longitude=lon, agents=agents)
            if result.get("success"):
                print(f"  {c('✓', 'green')} {f.name} → HRI {result['bxpHri']} [{result['level']}]")
                ok += 1
            else:
                print(f"  {c('✗', 'red')} {f.name} → {result.get('error')}")
                fail += 1
        except Exception as e:
            print(f"  {c('✗', 'red')} {f.name} → {e}")
            fail += 1

    print_sep()
    print(f"  Submitted: {c(str(ok), 'green')}  Failed: {c(str(fail), 'red')}")
    print()


def cmd_export(args):
    """Export a .bxp.json file to CSV or GeoJSON."""
    path = args.file
    if not Path(path).exists():
        print(c(f"Error: File not found: {path}", "red"))
        sys.exit(1)

    record = read_bxp(path)
    fmt    = (args.format or "csv").lower()

    if fmt == "csv":
        output = args.output or Path(path).stem + ".csv"
        buf = io.StringIO()
        w   = csv.writer(buf)
        # Header
        w.writerow([
            "bxpVersion", "deviceUuid", "geohash", "latitude", "longitude",
            "timestampUs", "durationS", "indoorOutdoor",
            "bxpHri", "bxpHriLevel", "qualityFlag",
            "agentId", "value", "unit",
        ])
        base = [
            record.get("bxpVersion", ""),
            record.get("deviceUuid", ""),
            record.get("geohash", ""),
            record.get("latitude", ""),
            record.get("longitude", ""),
            record.get("timestampUs", ""),
            record.get("durationS", ""),
            record.get("indoorOutdoor", ""),
            record.get("bxpHri", ""),
            record.get("bxpHriLevel", ""),
            record.get("quality", {}).get("flag", ""),
        ]
        agents = record.get("agents", [])
        if agents:
            for a in agents:
                w.writerow(base + [a.get("agentId",""), a.get("value",""), a.get("unit","")])
        else:
            w.writerow(base + ["", "", ""])
        Path(output).write_text(buf.getvalue(), encoding="utf-8")
        print(c(f"  Exported CSV: {output}", "green"))

    elif fmt == "geojson":
        output = args.output or Path(path).stem + ".geojson"
        lat = record.get("latitude")
        lon = record.get("longitude")
        if lat is None or lon is None:
            print(c("  Error: No coordinates in file", "red"))
            sys.exit(1)
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {k: v for k, v in record.items()
                           if not k.startswith("_")},
        }
        Path(output).write_text(
            json.dumps({"type": "FeatureCollection", "features": [feature]},
                       indent=2, default=str),
            encoding="utf-8"
        )
        print(c(f"  Exported GeoJSON: {output}", "green"))

    else:
        print(c(f"  Unknown format: {fmt}. Use csv or geojson.", "red"))
        sys.exit(1)


def cmd_server_status(args):
    url    = get_server_url(getattr(args, "server", None))
    client = BXPClient(url)
    print()
    print(bold(f"  BXP Server: {c(url, 'cyan')}"))
    print_sep()
    health = client.health()
    if health.get("status") == "ok":
        d = health.get("data", {})
        print(f"  Status:    {c('ONLINE', 'green')}")
        print(f"  BXP:       v{d.get('bxpVersion', '?')}")
        print(f"  Node Type: {d.get('nodeType', '?')}")
        print(f"  Readings:  {d.get('readingCount', '?')}")
        print(f"  Uptime:    {d.get('uptime', '?')}")
        aqicn = health.get("aqicnEnabled")
        if aqicn is not None:
            status = c("enabled", "green") if aqicn else c("disabled — set AQICN_TOKEN", "yellow")
            print(f"  AQICN:     {status}")
    else:
        print(f"  Status:    {c('OFFLINE', 'red')}")
    print()


def cmd_map(args):
    """Generate a self-contained HTML map from a folder of .bxp.json files."""
    directory = Path(args.dir)
    if not directory.is_dir():
        print(c(f"Error: Not a directory: {args.dir}", "red"))
        sys.exit(1)

    files = list(directory.glob("*.bxp.json"))
    if not files:
        print(c(f"No .bxp.json files found in {args.dir}", "yellow"))
        sys.exit(0)

    features = []
    for f in files:
        try:
            record = read_bxp(f)
            lat = record.get("latitude")
            lon = record.get("longitude")
            if lat is None or lon is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "hri":        record.get("bxpHri", 0),
                    "level":      record.get("bxpHriLevel", ""),
                    "geohash":    record.get("geohash", ""),
                    "deviceUuid": record.get("deviceUuid", ""),
                    "timestamp":  record.get("generatedAt", ""),
                    "file":       f.name,
                    "agents":     record.get("agents", []),
                },
            })
        except Exception:
            pass

    geojson = json.dumps({"type": "FeatureCollection", "features": features},
                         default=str)
    output  = args.output or "bxp_map.html"

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>BXP Map — {directory.name}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#060b18;color:#e8edf5;font-family:sans-serif}}
h1{{padding:0.75rem 1.5rem;font-size:1rem;color:#00d4ff;
  font-family:monospace;background:#060b18;border-bottom:1px solid #1a2540}}
#map{{height:calc(100vh - 42px)}}
</style>
</head>
<body>
<h1>BXP Map — {directory.name} ({len(features)} readings)</h1>
<div id="map"></div>
<script>
const DATA = {geojson};
const HRI_COLOR = hri =>
  hri<=20?'#00E676':hri<=40?'#FFEB3B':hri<=60?'#FF9800':
  hri<=75?'#F44336':hri<=90?'#9C27B0':'#4A0000';

const map = L.map('map').setView([20,10],2);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',
  {{attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19}}).addTo(map);

L.geoJSON(DATA, {{
  pointToLayer: (f,ll) => L.circleMarker(ll,{{
    radius:12, fillColor:HRI_COLOR(f.properties.hri),
    color:HRI_COLOR(f.properties.hri), weight:2,
    opacity:0.9, fillOpacity:0.5,
  }}),
  onEachFeature: (f,layer) => {{
    const p = f.properties;
    const agents = (p.agents||[]).map(a=>`${{a.agentId}}: ${{a.value}}`).join('<br>');
    layer.bindPopup(`<b>${{p.file}}</b><br>HRI: ${{p.hri}} [${{p.level}}]<br>
      Geohash: ${{p.geohash}}<br>${{agents}}`);
  }}
}}).addTo(map);
</script>
</body></html>"""

    Path(output).write_text(html, encoding="utf-8")
    print(c(f"  Map generated: {output} ({len(features)} reading(s))", "green"))


def cmd_config(args):
    """Manage ~/.bxp/config.json."""
    cfg = load_config()

    if args.config_cmd == "show":
        print()
        print(bold("  BXP Config (~/.bxp/config.json)"))
        print_sep()
        if not cfg:
            print(c("  (empty)", "gray"))
        else:
            for k, v in cfg.items():
                val = "***" if k in ("token",) else v
                print(f"  {k:<20} {val}")
        print()

    elif args.config_cmd == "set":
        key = args.key
        val = args.val
        cfg[key] = val
        save_config(cfg)
        print(c(f"  Set {key} = {val if key != 'token' else '***'}", "green"))

    elif args.config_cmd == "unset":
        key = args.key
        if key in cfg:
            del cfg[key]
            save_config(cfg)
            print(c(f"  Removed {key}", "green"))
        else:
            print(c(f"  Key not found: {key}", "yellow"))


# ─── Argument parser ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="bxp",
        description="BXP — Breathe Exposure Protocol CLI v2.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  bxp generate --pm25 47.2 --lat 5.6037 --lon -0.1870
  bxp generate --pm25 47.2 --no2 18.3 --temp 29 --lat 5.60 --lon -0.18
  bxp read reading.bxp.json
  bxp validate reading.bxp.json
  bxp export reading.bxp.json --format csv
  bxp export reading.bxp.json --format geojson --output out.geojson
  bxp hri --pm25 67.0 --no2 31.0 --duration 24h --population sensitive
  bxp submit --file reading.bxp.json
  bxp batch-submit --dir ./readings/
  bxp map ./readings/ --output map.html
  bxp server-status
  bxp config set server https://my-bxp-node.example.com
  bxp config set token bxp_abc123
  bxp config show
        """
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # ── generate ────────────────────────────────────────────────
    gen = sub.add_parser("generate", help="Generate a .bxp.json file")
    gen.add_argument("--lat",    type=float, help="Latitude (-90 to 90)")
    gen.add_argument("--lon",    type=float, help="Longitude (-180 to 180)")
    gen.add_argument("--gh",     type=str,   help="Geohash (min precision 5)")
    for a, h in [("--pm25","PM2.5 μg/m³"),("--pm10","PM10 μg/m³"),
                  ("--no2","NO2 ppb"),("--o3","O3 ppb"),("--co","CO ppm"),
                  ("--so2","SO2 ppb"),("--tvoc","TVOC ppb"),("--benz","Benzene ppb"),
                  ("--form","Formaldehyde ppb"),("--temp","Temperature °C"),
                  ("--rh","Rel. Humidity %"),("--press","Pressure hPa"),
                  ("--uv","UV Index"),("--co2","CO2 ppm"),("--pm1","PM1 μg/m³")]:
        gen.add_argument(a, type=float, help=h)
    gen.add_argument("--location", type=str, help="Location name (metadata)")
    gen.add_argument("--indoor",   action="store_true", help="Indoor measurement")
    gen.add_argument("--output",   type=str, help="Output filename")
    gen.add_argument("--device-uuid", dest="device_uuid", type=str)
    gen.add_argument("--verbose",  action="store_true", help="Print full record")

    # ── read ───────────────────────────────────────────────────
    rd = sub.add_parser("read", help="Read and display a .bxp.json file")
    rd.add_argument("file", help="Path to .bxp.json file")
    rd.add_argument("--raw", action="store_true", help="Print raw JSON")

    # ── validate ───────────────────────────────────────────────
    vl = sub.add_parser("validate", help="Validate a .bxp.json file")
    vl.add_argument("file", help="Path to .bxp.json file")

    # ── export ─────────────────────────────────────────────────
    ex = sub.add_parser("export", help="Export .bxp.json to CSV or GeoJSON")
    ex.add_argument("file",       help="Path to .bxp.json file")
    ex.add_argument("--format",   choices=["csv","geojson"], default="csv")
    ex.add_argument("--output",   type=str, help="Output file path")

    # ── hri ────────────────────────────────────────────────────
    hi = sub.add_parser("hri", help="Calculate BXP_HRI from values")
    for a in ["--pm25","--pm10","--no2","--o3","--co","--so2","--tvoc"]:
        hi.add_argument(a, type=float)
    hi.add_argument("--duration",   choices=["1h","8h","24h"], default="1h")
    hi.add_argument("--population", choices=["general","sensitive"], default="general")

    # ── submit ─────────────────────────────────────────────────
    sb = sub.add_parser("submit", help="Submit a .bxp.json to a BXP server")
    sb.add_argument("--server", type=str, help="Server URL (or use BXP_SERVER_URL)")
    sb.add_argument("--file",   type=str, required=True)
    sb.add_argument("--token",  type=str, help="Device token (or BXP_DEVICE_TOKEN)")

    # ── batch-submit ───────────────────────────────────────────
    bs = sub.add_parser("batch-submit",
                        help="Submit all .bxp.json files in a directory")
    bs.add_argument("--dir",    type=str, required=True, help="Directory of .bxp.json files")
    bs.add_argument("--server", type=str, help="Server URL")
    bs.add_argument("--token",  type=str, help="Device token")

    # ── map ────────────────────────────────────────────────────
    mp = sub.add_parser("map", help="Generate HTML map from a folder of readings")
    mp.add_argument("dir",     help="Directory of .bxp.json files")
    mp.add_argument("--output",type=str, default="bxp_map.html")

    # ── server-status ─────────────────────────────────────────
    ss = sub.add_parser("server-status", help="Check a BXP server")
    ss.add_argument("--server", type=str, help="Server URL")

    # ── config ─────────────────────────────────────────────────
    cfg_p = sub.add_parser("config", help="Manage BXP config (~/.bxp/config.json)")
    cfg_sub = cfg_p.add_subparsers(dest="config_cmd")
    cfg_sub.add_parser("show", help="Show current config")
    cs = cfg_sub.add_parser("set", help="Set a config key")
    cs.add_argument("key");  cs.add_argument("val")
    cu = cfg_sub.add_parser("unset", help="Remove a config key")
    cu.add_argument("key")

    args = parser.parse_args()

    if not args.command:
        print()
        print(bold("  BXP — Breathe Exposure Protocol CLI v2.1"))
        print(c("  Apache 2.0 | https://github.com/bxpprotocol/bxp-spec", "gray"))
        print()
        parser.print_help()
        print()
        sys.exit(0)

    dispatch = {
        "generate":      cmd_generate,
        "read":          cmd_read,
        "validate":      cmd_validate,
        "export":        cmd_export,
        "hri":           cmd_hri,
        "submit":        cmd_submit,
        "batch-submit":  cmd_batch_submit,
        "map":           cmd_map,
        "server-status": cmd_server_status,
        "config":        cmd_config,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
