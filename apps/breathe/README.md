# Breathe

Personal air-quality exposure tracker. Breathe is an **application built on** BXP — it does
not define, extend, or depend on parts of BXP that are not published.

## Status

Experimental. Single-file client-side app, no build step, no server, no account.

## What it does

- Reads PM2.5 / PM10 / NO2 / O3 from public endpoints (OpenAQ, WAQI) for your location
- Scores the current reading on a deliberately simple, explainable 0–100 scale
- Builds a local exposure history in IndexedDB
- Exports/imports that history as JSON
- Never sends your readings anywhere

## What it deliberately does not do

- No server, no sync, no analytics, no telemetry
- No API keys, no accounts, no tracking pixels
- No medical advice. The score is a coarse communication aid, not a health assessment.

## Honest limitations

These are real and worth knowing before treating any of it as dependable:

1. **CORS proxy.** OpenAQ and WAQI do not send `Access-Control-Allow-Origin`, so requests go
   through `corsproxy.io`. That is a third party in the data path. It can be slow, rate-limited,
   or unavailable, and it sees the requests (not your history — history never leaves the device).
   If that trade-off is unacceptable, the app degrades to showing no data rather than sending
   anything anywhere else.
2. **WAQI returns an index, not a concentration.** Breathe labels these `AQI` instead of
   presenting them as µg/m³, because the two are not interchangeable.
3. **Coverage is uneven.** Between OpenAQ and WAQI, many cities have a nearby station; some
   have none. Empty results are shown as empty, not guessed.
4. **Sampling only happens while the tab is open.** There is no background location service.
   That is a deliberate battery/privacy trade-off, not an oversight.
5. **The score is not validated.** It is a linear banding of PM2.5 against the WHO 24h
   guideline (15 µg/m³). It carries no clinical meaning and no regulatory standing.
6. **Not BXP-conformant output yet.** Export is Breathe's own JSON shape, not a `.bxp` record.
   Interop with real BXP nodes is roadmap work, not done.

## Running it

Open `breathe.html` directly in a browser, or serve the folder:

```
python -m http.server 8000
```

Then visit `http://localhost:8000/breathe.html`.

## Relationship to BXP

See [`../../SPEC.md`](../../SPEC.md) for the standard. The intended end state is for Breathe to
read and write real `.bxp` records so its history is portable to any BXP node.
