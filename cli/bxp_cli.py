#!/usr/bin/env python3
"""
BXP Command Line Tool v2.0
Breathe Exposure Protocol

Usage:
    python bxp_cli.py generate --pm25 47.2 --lat 5.6037 --lon -0.1870
    python bxp_cli.py read reading.bxp.json
    python bxp_cli.py validate reading.bxp.json
    python bxp_cli.py submit --server http://localhost:8000 --file reading.bxp.json
    python bxp_cli.py hri --pm25 67.0 --no2 31.0
    python bxp_cli.py server-status --server http://localhost:8000

Install globally:
    pip install bxp-sdk
    bxp generate --pm25 35 --lat 5.60 --lon -0.18
"""

import sys
import json
import argparse
import os
from pathlib import Path
from datetime import datetime, timezone

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent / "sdk" / "python"))
from bxp_sdk import (
    write_bxp, read_bxp, validate_bxp, calculate_risk,
    encode_geohash, BXPClient, BXP_VERSION, RISK_LEVELS
)


# ─────────────────────────────────────────────────────────────
# COLOR OUTPUT
# ─────────────────────────────────────────────────────────────

COLORS = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "green":   "\033[92m",
    "yellow":  "\033[93m",
    "red":     "\033[91m",
    "blue":    "\033[94m",
    "cyan":    "\033[96m",
    "magenta": "\033[95m",
    "gray":    "\033[90m",
    "white":   "\033[97m",
}

LEVEL_COLORS = {
    "CLEAN":     "green",
    "MODERATE":  "yellow",
    "ELEVATED":  "yellow",
    "HIGH":      "red",
    "VERY_HIGH": "red",
    "HAZARDOUS": "magenta",
}


def c(text: str, color: str) -> str:
    """Colorize text for terminal output."""
    if sys.stdout.isatty():
        return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"
    return text


def bold(text: str) -> str:
    return c(text, "bold")


def print_separator():
    print(c("─" * 60, "gray"))


def print_hri_banner(score: float, level: str, advice: str):
    level_color = LEVEL_COLORS.get(level, "white")
    print()
    print_separator()
    print(f"  {bold('BXP Health Risk Index')}  "
          f"{c(f'{score}', level_color)}  "
          f"{c(f'[{level}]', level_color)}")
    print(f"  {c(advice, 'gray')}")
    print_separator()
    print()


# ─────────────────────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────────────────────

def cmd_generate(args):
    """Generate a .bxp.json file from command line arguments."""

    output = args.output or f"reading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bxp.json"

    data = {}

    if args.lat:  data["latitude"]  = float(args.lat)
    if args.lon:  data["longitude"] = float(args.lon)
    if args.gh:   data["geohash"]   = args.gh

    # Agent values
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
        record = write_bxp(output, data,
                           device_uuid=args.device_uuid)

        print()
        print(bold(f"  BXP file generated: {c(output, 'cyan')}"))
        print_separator()

        if record.get("geohash"):
            print(f"  Geohash:    {c(record['geohash'], 'cyan')}")
        if record.get("latitude"):
            print(f"  Location:   {record['latitude']}, {record['longitude']}")

        agents = record.get("agents", [])
        if agents:
            print(f"  Agents:     {len(agents)}")
            for a in agents:
                who = ""
                from bxp_sdk import WHO_THRESHOLDS
                if a["agentId"] in WHO_THRESHOLDS:
                    thr = WHO_THRESHOLDS[a["agentId"]]
                    if float(a["value"]) > thr:
                        who = c(f"  ↑ EXCEEDS WHO ({thr})", "red")
                    else:
                        who = c(f"  ✓ within WHO ({thr})", "green")
                print(f"  {c('  ' + a['agentId'], 'gray')}: "
                      f"{a['value']} {a['unit']}{who}")

        hri   = record.get("bxpHri", 0)
        level = record.get("bxpHriLevel", "CLEAN")
        advice = next(
            (la for lo, hi, ln, lc, la, _ in RISK_LEVELS
             if lo <= hri <= hi), ""
        )
        print_hri_banner(hri, level, advice)

        if args.verbose:
            print(c("  Full record:", "gray"))
            print(json.dumps(record, indent=2, default=str))

    except Exception as e:
        print(c(f"Error generating file: {e}", "red"))
        sys.exit(1)


def cmd_read(args):
    """Read and display a .bxp.json file."""

    path = args.file
    if not Path(path).exists():
        print(c(f"Error: File not found: {path}", "red"))
        sys.exit(1)

    record = read_bxp(path)

    print()
    print(bold(f"  BXP Record: {c(path, 'cyan')}"))
    print_separator()

    print(f"  BXP Version:  {record.get('bxpVersion', '?')}")
    print(f"  Device UUID:  {c(record.get('deviceUuid', '?'), 'gray')}")
    print(f"  Geohash:      {c(record.get('geohash', '?'), 'cyan')}")

    ts = record.get("timestampUs")
    if ts:
        dt = datetime.fromtimestamp(ts / 1_000_000, tz=timezone.utc)
        print(f"  Timestamp:    {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    if record.get("latitude"):
        print(f"  Location:     {record['latitude']}, {record['longitude']}")

    quality = record.get("quality", {})
    qflag = quality.get("flag", "?")
    qcol  = "green" if qflag == "VALIDATED" else (
            "yellow" if qflag == "UNVALIDATED" else "red")
    print(f"  Quality:      {c(qflag, qcol)} "
          f"({quality.get('confidence', 0) * 100:.0f}% confidence)")

    integrity = record.get("_integrityOk")
    if integrity is True:
        print(f"  Integrity:    {c('✓ Hash verified', 'green')}")
    elif integrity is False:
        print(f"  Integrity:    {c('✗ Hash mismatch — possible tampering', 'red')}")

    print_separator()
    print(f"  {'Agent':<10} {'Value':<12} {'Unit':<10} {'WHO Limit':<12} Status")
    print_separator()

    from bxp_sdk import WHO_THRESHOLDS
    for a in record.get("agents", []):
        aid  = a.get("agentId", "?")
        val  = a.get("value", 0)
        unit = a.get("unit", "")
        thr  = WHO_THRESHOLDS.get(aid)
        if thr:
            over  = float(val) > thr
            thr_s = str(thr)
            stat  = c("↑ EXCEEDS", "red") if over else c("✓ OK", "green")
        else:
            thr_s = "—"
            stat  = c("—", "gray")
        print(f"  {aid:<10} {str(val):<12} {unit:<10} {thr_s:<12} {stat}")

    hri   = record.get("bxpHri", 0)
    level = record.get("bxpHriLevel", "")
    advice = next(
        (la for lo, hi, ln, lc, la, _ in RISK_LEVELS
         if lo <= hri <= hi), ""
    )
    print_hri_banner(hri, level, advice)

    if args.raw:
        print(c("  Raw JSON:", "gray"))
        print(json.dumps(
            {k: v for k, v in record.items()
             if not k.startswith("_")},
            indent=2, default=str
        ))


def cmd_validate(args):
    """Validate a .bxp.json file against the BXP v2.0 spec."""

    path = args.file
    if not Path(path).exists():
        print(c(f"Error: File not found: {path}", "red"))
        sys.exit(1)

    result = validate_bxp(path)

    print()
    print(bold(f"  BXP Validation: {c(path, 'cyan')}"))
    print_separator()

    if result["valid"]:
        print(f"  Result:  {c('✓ VALID', 'green')}")
    else:
        print(f"  Result:  {c('✗ INVALID', 'red')}")

    print(f"  Summary: {result['summary']}")

    if result["errors"]:
        print()
        print(c("  Errors:", "red"))
        for e in result["errors"]:
            print(f"    {c('✗', 'red')} {e}")

    if result["warnings"]:
        print()
        print(c("  Warnings:", "yellow"))
        for w in result["warnings"]:
            print(f"    {c('⚠', 'yellow')} {w}")

    if result["valid"] and not result["warnings"]:
        print()
        print(c("  All checks passed. File is fully BXP v2.0 compliant.", "green"))

    print()
    sys.exit(0 if result["valid"] else 1)


def cmd_hri(args):
    """Calculate BXP_HRI from command line values."""

    kwargs = {}
    for key in ["pm25","pm10","no2","o3","co","so2","tvoc"]:
        val = getattr(args, key, None)
        if val is not None:
            kwargs[key] = float(val)

    if not kwargs:
        print(c("Error: Provide at least one measurement value.", "red"))
        print("Example: bxp hri --pm25 67.0 --no2 31.0")
        sys.exit(1)

    result = calculate_risk(
        **kwargs,
        duration=args.duration or "1h",
        population=args.population or "general"
    )

    print()
    print(bold("  BXP Health Risk Index Calculator"))
    print_separator()
    print(f"  Score:      {c(str(result['score']), LEVEL_COLORS.get(result['level'], 'white'))}")
    print(f"  Level:      {c(result['level'], LEVEL_COLORS.get(result['level'], 'white'))}")
    print(f"  Color:      {result['color']}")
    print(f"  Duration:   {result['duration']}")
    print(f"  Population: {result['population']}")
    print()
    print(f"  Advice:")
    print(f"    General:   {result['advice']}")
    print(f"    Sensitive: {result['sensitiveAdvice']}")
    print()
    if result["breakdown"]:
        print_separator()
        print(f"  {'Agent':<10} {'Value':<10} {'Risk':<8} {'Weight':<8} Contribution")
        print_separator()
        for aid, b in result["breakdown"].items():
            over = c(" ↑ EXCEEDS WHO", "red") if b["exceedsWho"] else ""
            print(f"  {aid:<10} {str(b['value']):<10} "
                  f"{b['normalizedRisk']:<8} "
                  f"{HRI_WEIGHTS.get(aid, 0):<8} "
                  f"{b['contribution']}{over}")
    print()


def cmd_submit(args):
    """Submit a .bxp.json file to a BXP server."""

    if not args.server:
        print(c("Error: --server required", "red"))
        sys.exit(1)

    client = BXPClient(args.server, device_token=args.token)

    # Check server health first
    print(c("  Checking server health...", "gray"))
    health = client.health()
    if health.get("status") != "ok":
        print(c(f"  Server unreachable or not BXP-compliant: {args.server}", "red"))
        sys.exit(1)
    print(c(f"  Server online: BXP v{health.get('data', {}).get('bxpVersion', '?')}", "green"))

    if args.file:
        record = read_bxp(args.file)
        lat = record.get("latitude")
        lon = record.get("longitude")
        agents = record.get("agents", [])

        if not lat or not lon:
            print(c("  Error: File has no coordinates", "red"))
            sys.exit(1)

        result = client.submit(
            latitude=lat, longitude=lon, agents=agents
        )
    else:
        print(c("  Error: --file required", "red"))
        sys.exit(1)

    if result.get("success"):
        print()
        print(bold("  Submission successful"))
        print_separator()
        print(f"  Reading ID:  {c(result['readingId'], 'cyan')}")
        print(f"  Geohash:     {result.get('geohash')}")
        print(f"  BXP_HRI:     {c(str(result['bxpHri']), 'yellow')} [{result['level']}]")
        print(f"  Quality:     {result['qualityFlag']}")
        print()
    else:
        print(c(f"  Submission failed: {result.get('error')}", "red"))
        sys.exit(1)


def cmd_server_status(args):
    """Check status of a BXP server."""

    url = args.server or "http://localhost:8000"
    client = BXPClient(url)

    print()
    print(bold(f"  BXP Server Status: {c(url, 'cyan')}"))
    print_separator()

    health = client.health()
    if health.get("status") == "ok":
        data = health.get("data", {})
        print(f"  Status:    {c('ONLINE', 'green')}")
        print(f"  BXP:       v{data.get('bxpVersion', '?')}")
        print(f"  Node Type: {data.get('nodeType', '?')}")
        print(f"  Readings:  {data.get('readingCount', '?')}")
        print(f"  Uptime:    {data.get('uptime', '?')}")
    else:
        print(f"  Status:    {c('OFFLINE or not BXP-compliant', 'red')}")
    print()


# ─────────────────────────────────────────────────────────────
# HRI_WEIGHTS needed for display
# ─────────────────────────────────────────────────────────────
HRI_WEIGHTS = {
    "PM2_5": 0.35, "PM10": 0.15, "NO2": 0.15,
    "O3": 0.12,    "CO": 0.10,   "SO2": 0.05,
    "TVOC": 0.04,  "BENZ": 0.02, "FORM": 0.02,
}


# ─────────────────────────────────────────────────────────────
# ARGUMENT PARSER
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="bxp",
        description="BXP — Breathe Exposure Protocol CLI v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  bxp generate --pm25 47.2 --lat 5.6037 --lon -0.1870
  bxp generate --pm25 47.2 --no2 18.3 --temp 29 --lat 5.60 --lon -0.18 --location "Accra Central"
  bxp read reading.bxp.json
  bxp validate reading.bxp.json
  bxp hri --pm25 67.0 --no2 31.0
  bxp hri --pm25 67.0 --duration 24h --population sensitive
  bxp submit --server http://localhost:8000 --file reading.bxp.json
  bxp server-status --server http://localhost:8000
        """
    )

    sub = parser.add_subparsers(dest="command", help="Command")

    # ── generate ──────────────────────────────────────────────
    gen = sub.add_parser("generate",
                         help="Generate a .bxp.json file")
    gen.add_argument("--lat",     type=float, help="Latitude")
    gen.add_argument("--lon",     type=float, help="Longitude")
    gen.add_argument("--gh",      type=str,   help="Geohash (alternative to lat/lon)")
    gen.add_argument("--pm25",    type=float, help="PM2.5 (μg/m³)")
    gen.add_argument("--pm10",    type=float, help="PM10 (μg/m³)")
    gen.add_argument("--no2",     type=float, help="NO2 (ppb)")
    gen.add_argument("--o3",      type=float, help="O3 (ppb)")
    gen.add_argument("--co",      type=float, help="CO (ppm)")
    gen.add_argument("--so2",     type=float, help="SO2 (ppb)")
    gen.add_argument("--tvoc",    type=float, help="TVOC (ppb)")
    gen.add_argument("--benz",    type=float, help="Benzene (ppb)")
    gen.add_argument("--form",    type=float, help="Formaldehyde (ppb)")
    gen.add_argument("--temp",    type=float, help="Temperature (°C)")
    gen.add_argument("--rh",      type=float, help="Relative Humidity (%)")
    gen.add_argument("--press",   type=float, help="Pressure (hPa)")
    gen.add_argument("--uv",      type=float, help="UV Index")
    gen.add_argument("--co2",     type=float, help="CO2 (ppm)")
    gen.add_argument("--pm1",     type=float, help="PM1 (μg/m³)")
    gen.add_argument("--location",type=str,   help="Location name (metadata)")
    gen.add_argument("--indoor",  action="store_true", help="Indoor measurement")
    gen.add_argument("--output",  type=str,   help="Output filename (.bxp.json)")
    gen.add_argument("--device-uuid", dest="device_uuid",
                     type=str, help="Device UUID")
    gen.add_argument("--verbose", action="store_true",
                     help="Print full record")

    # ── read ──────────────────────────────────────────────────
    rd = sub.add_parser("read", help="Read and display a .bxp.json file")
    rd.add_argument("file", help="Path to .bxp.json file")
    rd.add_argument("--raw", action="store_true",
                    help="Print raw JSON")

    # ── validate ──────────────────────────────────────────────
    vl = sub.add_parser("validate",
                         help="Validate a .bxp.json file")
    vl.add_argument("file", help="Path to .bxp.json file")

    # ── hri ───────────────────────────────────────────────────
    hi = sub.add_parser("hri",
                         help="Calculate BXP_HRI from values")
    hi.add_argument("--pm25",    type=float)
    hi.add_argument("--pm10",    type=float)
    hi.add_argument("--no2",     type=float)
    hi.add_argument("--o3",      type=float)
    hi.add_argument("--co",      type=float)
    hi.add_argument("--so2",     type=float)
    hi.add_argument("--tvoc",    type=float)
    hi.add_argument("--duration",   type=str, default="1h",
                    choices=["1h","8h","24h"])
    hi.add_argument("--population", type=str, default="general",
                    choices=["general","sensitive"])

    # ── submit ────────────────────────────────────────────────
    sb = sub.add_parser("submit",
                         help="Submit a .bxp.json to a BXP server")
    sb.add_argument("--server", type=str, required=True)
    sb.add_argument("--file",   type=str, required=True)
    sb.add_argument("--token",  type=str, help="Device token")

    # ── server-status ─────────────────────────────────────────
    ss = sub.add_parser("server-status",
                         help="Check a BXP server status")
    ss.add_argument("--server", type=str,
                    default="http://localhost:8000")

    args = parser.parse_args()

    if not args.command:
        print()
        print(bold("  BXP — Breathe Exposure Protocol CLI v2.0"))
        print(c("  Apache 2.0 | https://github.com/bxpprotocol/bxp-spec", "gray"))
        print()
        parser.print_help()
        print()
        sys.exit(0)

    dispatch = {
        "generate":      cmd_generate,
        "read":          cmd_read,
        "validate":      cmd_validate,
        "hri":           cmd_hri,
        "submit":        cmd_submit,
        "server-status": cmd_server_status,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
