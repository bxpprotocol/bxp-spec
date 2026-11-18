/**
 * BXP Protocol TypeScript/JavaScript SDK v2.1
 * Breathe Exposure Protocol
 *
 * Works in Node.js, browsers, and edge runtimes (Deno, Bun, Cloudflare Workers).
 *
 * Usage:
 *   import { BXPClient, calculateRisk, writeBxp } from 'bxp-sdk';
 *
 *   const risk = calculateRisk({ pm25: 67.0, no2: 31.0 });
 *   console.log(risk.score);   // 72.4
 *   console.log(risk.level);   // 'HIGH'
 *
 *   const client = new BXPClient('https://your-node.example.com', {
 *     deviceToken: 'bxp_...',
 *   });
 *   const result = await client.submit({ latitude: 5.60, longitude: -0.18, pm25: 47.2 });
 */

// ─── Types ────────────────────────────────────────────────────

export interface AgentReading {
  agentId: string;
  value: number;
  unit?: string;
}

export interface BxpRecord {
  bxpVersion: string;
  deviceUuid: string;
  geohash?: string;
  latitude?: number;
  longitude?: number;
  timestampUs: number;
  durationS?: number;
  indoorOutdoor?: 'indoor' | 'outdoor';
  agents: AgentReading[];
  context?: Record<string, unknown>;
  quality?: QualityInfo;
  bxpHri?: number;
  bxpHriLevel?: string;
  bxpHriColor?: string;
  generatedAt?: string;
  payloadHash?: string;
}

export interface QualityInfo {
  flag: 'VALIDATED' | 'UNVALIDATED' | 'SUSPECT' | 'INVALID';
  confidence: number;
  qcMethod: string;
  notes?: string[] | null;
}

export interface HriResult {
  score: number;
  level: 'CLEAN' | 'MODERATE' | 'ELEVATED' | 'HIGH' | 'VERY_HIGH' | 'HAZARDOUS';
  color: string;
  advice: string;
  sensitiveAdvice: string;
  duration: string;
  population: string;
  breakdown: Record<string, {
    value: number;
    threshold: number;
    normalizedRisk: number;
    contribution: number;
    exceedsWho: boolean;
  }>;
}

export interface SubmitOptions {
  latitude: number;
  longitude: number;
  pm25?: number;
  pm10?: number;
  no2?: number;
  o3?: number;
  co?: number;
  so2?: number;
  temp?: number;
  humidity?: number;
  agents?: AgentReading[];
  durationS?: number;
  indoor?: boolean;
}

export interface SubmitResult {
  success: boolean;
  readingId?: string;
  geohash?: string;
  bxpHri?: number;
  level?: string;
  qualityFlag?: string;
  error?: string;
}

export interface ReadingsPage {
  readings: BxpRecord[];
  total: number;
  offset: number;
  limit: number;
}

export interface BXPClientOptions {
  deviceToken?: string;
  deviceUuid?: string;
  timeout?: number;
}

// ─── Constants ────────────────────────────────────────────────

export const BXP_VERSION = '2.0';

export const WHO_THRESHOLDS: Record<string, number> = {
  PM2_5: 15.0, PM10: 45.0, NO2: 25.0,
  O3: 100.0,   CO: 4.0,    SO2: 40.0,
  TVOC: 500.0, BENZ: 1.0,  FORM: 8.0,
};

export const HRI_WEIGHTS: Record<string, number> = {
  PM2_5: 0.35, PM10: 0.15, NO2: 0.15,
  O3: 0.12,    CO: 0.10,   SO2: 0.05,
  TVOC: 0.04,  BENZ: 0.02, FORM: 0.02,
};

// Upper bound of each band. Bands are contiguous (no gaps): a score falls
// into the first band whose upper bound is >= score. Do not leave gaps
// between bands (e.g. 20/21, 40/41) — any score landing in a gap used to
// silently fall through to the CLEAN default. See bxp_sdk.py for the same fix.
const RISK_LEVELS: Array<[number, string, string, string, string]> = [
  [20,  'CLEAN',     '#00C851', 'No health risk.',           'Enjoy outdoor activities freely.'],
  [40,  'MODERATE',  '#FFBB33', 'Acceptable for most.',      'Sensitive groups: limit prolonged exertion.'],
  [60,  'ELEVATED',  '#FF8800', 'Reduce outdoor exertion.',  'Sensitive groups: avoid outdoor exertion.'],
  [75,  'HIGH',      '#CC0000', 'Wear N95 outdoors.',        'Sensitive groups: stay indoors.'],
  [90,  'VERY_HIGH', '#9B0000', 'Avoid all outdoor activity.', 'Everyone: stay indoors.'],
  [100, 'HAZARDOUS', '#4A0000', 'Emergency. Stay indoors.',  'Evacuate to cleaner air.'],
];

const AGENT_UNITS: Record<string, string> = {
  PM1: 'ug/m3', PM2_5: 'ug/m3', PM10: 'ug/m3',
  CO: 'ppm',    CO2: 'ppm',     NO2: 'ppb',
  SO2: 'ppb',   O3: 'ppb',      H2S: 'ppb',
  TVOC: 'ppb',  BENZ: 'ppb',   FORM: 'ppb',
  TEMP: 'C',    RH: '%',        PRESS: 'hPa',
  UV: 'index',  PB: 'ug/m3',   HG: 'ug/m3',
};

const BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz';


// ─── Geohash ──────────────────────────────────────────────────

export function encodeGeohash(lat: number, lon: number, precision = 7): string {
  let latRange = [-90.0, 90.0];
  let lonRange = [-180.0, 180.0];
  const bits = [16, 8, 4, 2, 1];
  let bi = 0, even = true, result = '', ch = 0;

  while (result.length < precision) {
    if (even) {
      const mid = (lonRange[0] + lonRange[1]) / 2;
      if (lon >= mid) { ch |= bits[bi]; lonRange[0] = mid; }
      else            { lonRange[1] = mid; }
    } else {
      const mid = (latRange[0] + latRange[1]) / 2;
      if (lat >= mid) { ch |= bits[bi]; latRange[0] = mid; }
      else            { latRange[1] = mid; }
    }
    even = !even;
    bi++;
    if (bi === 5) { result += BASE32[ch]; ch = 0; bi = 0; }
  }
  return result;
}


// ─── HRI calculation ──────────────────────────────────────────

export interface CalculateRiskOptions {
  pm25?: number;
  pm10?: number;
  no2?: number;
  o3?: number;
  co?: number;
  so2?: number;
  tvoc?: number;
  agents?: AgentReading[];
  duration?: '1h' | '8h' | '24h';
  population?: 'general' | 'sensitive';
}

export function calculateRisk(opts: CalculateRiskOptions): HriResult {
  const agentList: AgentReading[] = [...(opts.agents ?? [])];
  const named: Record<string, number | undefined> = {
    PM2_5: opts.pm25, PM10: opts.pm10, NO2: opts.no2,
    O3: opts.o3, CO: opts.co, SO2: opts.so2, TVOC: opts.tvoc,
  };
  for (const [aid, val] of Object.entries(named)) {
    if (val !== undefined) agentList.push({ agentId: aid, value: val });
  }

  const dFactor = { '1h': 1.0, '8h': 1.2, '24h': 1.5 }[opts.duration ?? '1h'] ?? 1.0;
  const vFactor = { general: 1.0, sensitive: 1.3 }[opts.population ?? 'general'] ?? 1.0;

  let raw = 0;
  const breakdown: HriResult['breakdown'] = {};

  for (const a of agentList) {
    const aid   = a.agentId;
    const val   = a.value;
    const thr   = WHO_THRESHOLDS[aid];
    const w     = HRI_WEIGHTS[aid] ?? 0;
    if (thr === undefined) continue;
    const risk  = Math.min(1.0, val / thr);
    const contrib = risk * w;
    raw += contrib;
    breakdown[aid] = {
      value: val, threshold: thr,
      normalizedRisk: Math.round(risk * 10000) / 10000,
      contribution:   Math.round(contrib * 10000) / 10000,
      exceedsWho: val > thr,
    };
  }

  const score  = Math.round(Math.min(100, raw * 100 * dFactor * vFactor) * 100) / 100;
  const fallback = RISK_LEVELS[RISK_LEVELS.length - 1];
  let [, level, color, advice, sadv] = fallback;
  for (const [hi, ln, lc, la, lsa] of RISK_LEVELS) {
    if (score <= hi) {
      level = ln; color = lc; advice = la; sadv = lsa; break;
    }
  }

  return {
    score, level: level as HriResult['level'],
    color, advice, sensitiveAdvice: sadv,
    duration: opts.duration ?? '1h',
    population: opts.population ?? 'general',
    breakdown,
  };
}


// ─── SHA-256 (cross-env) ──────────────────────────────────────

async function sha256hex(data: string): Promise<string> {
  // Node.js
  try {
    const { createHash } = await import('crypto' as any);
    return createHash('sha256').update(data).digest('hex');
  } catch { /* not Node.js */ }
  // Browser / Deno / Bun
  const buf = await crypto.subtle.digest(
    'SHA-256', new TextEncoder().encode(data)
  );
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0')).join('');
}


// ─── Write BXP record ─────────────────────────────────────────

export async function writeBxp(
  data: Partial<BxpRecord> & { latitude?: number; longitude?: number } & Record<string, unknown>,
  deviceUuid?: string,
): Promise<BxpRecord> {
  const devUuid = deviceUuid ?? crypto.randomUUID();
  const nowUs   = Date.now() * 1000;
  const lat     = data.latitude as number | undefined;
  const lon     = data.longitude as number | undefined;

  if (lat !== undefined && (lat < -90 || lat > 90))
    throw new Error(`latitude ${lat} out of range`);
  if (lon !== undefined && (lon < -180 || lon > 180))
    throw new Error(`longitude ${lon} out of range`);

  const geohash = data.geohash ??
    (lat !== undefined && lon !== undefined ? encodeGeohash(lat, lon, 7) : undefined);

  if (geohash && geohash.length < 5)
    throw new Error(`Geohash precision too low: ${geohash.length} (minimum 5)`);

  const agents: AgentReading[] = [...(data.agents ?? [])];
  const shorthand: Record<string, keyof typeof AGENT_UNITS | undefined> = {
    pm25: 'PM2_5', pm10: 'PM10', no2: 'NO2', o3: 'O3',
    co: 'CO', so2: 'SO2', tvoc: 'TVOC', temp: 'TEMP',
    humidity: 'RH', pressure: 'PRESS', co2: 'CO2',
  };
  for (const [key, aid] of Object.entries(shorthand)) {
    const val = (data as any)[key];
    if (val !== undefined && aid) {
      agents.push({ agentId: aid, value: val, unit: AGENT_UNITS[aid] });
    }
  }
  if (!agents.length) throw new Error('At least one agent value is required');

  const hri = calculateRisk({ agents });

  const record: BxpRecord = {
    bxpVersion: BXP_VERSION,
    deviceUuid: devUuid,
    geohash,
    latitude: lat,
    longitude: lon,
    timestampUs: (data.timestampUs as number) ?? nowUs,
    durationS: (data.durationS as number) ?? 60,
    indoorOutdoor: (data.indoorOutdoor as 'indoor' | 'outdoor') ?? 'outdoor',
    agents,
    context: data.context as Record<string, unknown> | undefined,
    quality: {
      flag: 'UNVALIDATED', confidence: 0.9,
      qcMethod: 'bxp-sdk-ts-auto', notes: null,
    },
    bxpHri:      hri.score,
    bxpHriLevel: hri.level,
    bxpHriColor: hri.color,
    generatedAt: new Date().toISOString(),
  };

  const payload = JSON.stringify(record, Object.keys(record).sort(), 0);
  record.payloadHash = 'sha256:' + await sha256hex(payload);
  return record;
}


// ─── HTTP Client ──────────────────────────────────────────────

export class BXPClient {
  private baseUrl: string;
  private deviceToken?: string;
  readonly deviceUuid: string;
  private timeout: number;

  constructor(baseUrl?: string, opts: BXPClientOptions = {}) {
    this.baseUrl      = (baseUrl ?? (
      typeof process !== 'undefined'
        ? (process.env.BXP_SERVER_URL ?? 'http://localhost:5000')
        : 'http://localhost:5000'
    )).replace(/\/$/, '');
    this.deviceToken  = opts.deviceToken;
    this.deviceUuid   = opts.deviceUuid ?? crypto.randomUUID();
    this.timeout      = opts.timeout ?? 15000;
  }

  private get headers(): Record<string, string> {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.deviceToken) h['Authorization'] = `Bearer ${this.deviceToken}`;
    return h;
  }

  private async req<T = unknown>(
    method: string, path: string, body?: unknown
  ): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeout);
    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      const text = await resp.text();
      try { return JSON.parse(text) as T; }
      catch { return text as unknown as T; }
    } finally {
      clearTimeout(timer);
    }
  }

  async health(): Promise<Record<string, unknown>> {
    return this.req('GET', '/bxp/v2/health');
  }

  async submit(opts: SubmitOptions): Promise<SubmitResult> {
    const agents: AgentReading[] = [...(opts.agents ?? [])];
    const named: Record<string, number | undefined> = {
      PM2_5: opts.pm25, PM10: opts.pm10, NO2: opts.no2,
      O3: opts.o3, CO: opts.co, SO2: opts.so2,
    };
    for (const [aid, val] of Object.entries(named)) {
      if (val !== undefined)
        agents.push({ agentId: aid, value: val, unit: AGENT_UNITS[aid] });
    }

    const body = { readings: [{
      deviceUuid:    this.deviceUuid,
      latitude:      opts.latitude,
      longitude:     opts.longitude,
      timestampUs:   Date.now() * 1000,
      agents,
      durationS:     opts.durationS ?? 60,
      indoorOutdoor: opts.indoor ? 'indoor' : 'outdoor',
    }] };

    const resp = await this.req<any>('POST', '/bxp/v2/readings', body);
    if (resp?.status === 'ok') {
      const r = resp.data.readings[0];
      return {
        success: true, readingId: r.readingId, geohash: r.geohash,
        bxpHri: r.bxpHri, level: r.bxpHriLevel, qualityFlag: r.qualityFlag,
      };
    }
    return { success: false, error: resp?.detail ?? 'Unknown error' };
  }

  async getReadings(opts: {
    geohash?: string; limit?: number; offset?: number;
    quality?: string; fromTs?: number; toTs?: number;
  } = {}): Promise<ReadingsPage> {
    const qs = new URLSearchParams();
    if (opts.geohash) qs.set('geohash', opts.geohash);
    if (opts.limit)   qs.set('limit',   String(opts.limit));
    if (opts.offset)  qs.set('offset',  String(opts.offset));
    if (opts.quality) qs.set('quality', opts.quality);
    if (opts.fromTs)  qs.set('from_ts', String(opts.fromTs));
    if (opts.toTs)    qs.set('to_ts',   String(opts.toTs));
    const resp = await this.req<any>('GET', `/bxp/v2/readings?${qs}`);
    return {
      readings: resp?.data?.readings ?? [],
      total:    resp?.total ?? 0,
      offset:   resp?.offset ?? 0,
      limit:    resp?.limit  ?? 50,
    };
  }

  async getAllReadings(opts: { geohash?: string; pageSize?: number } = {}): Promise<BxpRecord[]> {
    const all: BxpRecord[] = [];
    let offset = 0;
    const limit = opts.pageSize ?? 50;
    while (true) {
      const page = await this.getReadings({ ...opts, limit, offset });
      all.push(...page.readings);
      if (page.readings.length < limit) break;
      offset += limit;
      if (offset >= page.total) break;
    }
    return all;
  }

  async getCity(city: string): Promise<Record<string, unknown> | null> {
    const resp = await this.req<any>('GET', `/bxp/v2/city/${encodeURIComponent(city)}`);
    return resp?.bxp_hri ? resp : null;
  }

  async getLatest(geohash: string): Promise<Record<string, unknown> | null> {
    const resp = await this.req<any>('GET', `/bxp/v2/locations/${geohash}/latest`);
    return resp?.status === 'ok' ? resp.data : null;
  }

  async registerDevice(label?: string): Promise<Record<string, unknown>> {
    const resp = await this.req<any>('POST', '/bxp/v2/devices/register', {
      deviceUuid: this.deviceUuid, label,
    });
    if (resp?.status === 'ok' && resp.data?.token) {
      this.deviceToken = resp.data.token;
    }
    return resp;
  }

  async deleteReading(readingId: string): Promise<Record<string, unknown>> {
    return this.req('DELETE', `/bxp/v2/readings/${readingId}`);
  }

  async verifyReading(readingId: string): Promise<Record<string, unknown>> {
    return this.req('GET', `/bxp/v2/readings/${readingId}/verify`);
  }

  async submitReport(opts: {
    latitude: number; longitude: number;
    reportType?: string; description?: string; severity?: string;
  }): Promise<Record<string, unknown>> {
    return this.req('POST', '/bxp/v2/community/reports', opts);
  }

  async search(opts: {
    q?: string; lat?: number; lon?: number; limit?: number;
  }): Promise<Record<string, unknown>[]> {
    const qs = new URLSearchParams();
    if (opts.q)     qs.set('q',   opts.q);
    if (opts.lat)   qs.set('lat', String(opts.lat));
    if (opts.lon)   qs.set('lon', String(opts.lon));
    if (opts.limit) qs.set('limit', String(opts.limit));
    const resp = await this.req<any>('GET', `/bxp/v2/search?${qs}`);
    return resp?.data?.results ?? [];
  }

  async metrics(): Promise<string> {
    return this.req('GET', '/metrics');
  }


// ─────────────────────────────────────────────────────────────
// PERSONAL EXPOSURE RECORDS — PROOF-CARRYING LEDGER (SPEC §10.5)
// ─────────────────────────────────────────────────────────────

export const EXPOSURE_SOURCES = new Set(["open-meteo", "bxp-node", "sensor", "manual"]);
export const EXPOSURE_MEASUREMENT_TYPES = new Set(["measured", "modelled", "manual"]);
export const LOCATION_PRECISIONS = new Set(["none", "city", "area", "exact"]);

export const WHO_PM25_24H = 15.0;
export const WHO_PM10_24H = 45.0;
export const WHO_NO2_24H  = 25.0;

export interface ExposureEntry {
  recordType:        "exposure";
  timestampUs:       number;
  location:          { lat?: number | null; lon?: number | null; geohash?: string | null };
  agents:            AgentReading[];
  source:            string;
  measurementType:   string;
  locationPrecision: string;
  qualityNotes:      string[];
  previousHash:      string | null;
  entryHash:         string;
}

export interface ExposureChainResult {
  valid:             boolean;
  errors:            string[];
  firstBrokenIndex:  number | null;
  entryCount:        number;
}

/**
 * Stable, compact JSON for hash computation — matches Python exactly:
 * json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)
 */
export function stableStringify(obj: unknown): string {
  return JSON.stringify(stableSort(obj));
}

function stableSort(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(stableSort);
  const obj = value as Record<string, unknown>;
  const sorted: Record<string, unknown> = {};
  for (const key of Object.keys(obj).sort()) {
    sorted[key] = stableSort(obj[key]);
  }
  return sorted;
}

export function entryHash(entry: ExposureEntry): string {
  const check = { ...entry };
  delete check.entryHash;
  const payload = stableStringify(check);
  return "sha256:" + sha256hexSync(payload);
}

/**
 * Synchronous SHA-256 hex digest. Works in Node (crypto) and browsers (SubtleCrypto).
 * For browsers, falls back to async — callers in async contexts should await sha256hex.
 * Here we need sync, so use a small sync implementation for environments without crypto.subtle.
 */
export function sha256hexSync(data: string): string {
  // Node.js
  try {
    const { createHash } = require("crypto");
    return createHash("sha256").update(data, "utf8").digest("hex");
  } catch { /* not Node.js or require not available */ }
  // Browser / Deno / Bun — synchronous SubtleCrypto is not available.
  // Fall back: this path should not be hit in browser async code;
  // createExposureEntry is async in browser environments.
  throw new Error("Synchronous SHA-256 not available in this environment. Use async createExposureEntry.");
}

export async function createExposureEntry(
  agents: AgentReading[],
  opts: {
    source?: string;
    measurementType?: string;
    location?: { lat?: number | null; lon?: number | null; geohash?: string | null };
    previousHash?: string | null;
    locationPrecision?: string;
    qualityNotes?: string[];
    timestampUs?: number;
  } = {},
): Promise<ExposureEntry> {
  const {
    source = "manual",
    measurementType = "manual",
    location = { lat: null, lon: null },
    previousHash = null,
    locationPrecision = "area",
    qualityNotes = [],
    timestampUs,
  } = opts;

  if (!EXPOSURE_SOURCES.has(source))
    throw new Error(`Invalid source '${source}' — must be one of: ${[...EXPOSURE_SOURCES].sort().join(", ")}`);
  if (!EXPOSURE_MEASUREMENT_TYPES.has(measurementType))
    throw new Error(`Invalid measurementType '${measurementType}' — must be one of: ${[...EXPOSURE_MEASUREMENT_TYPES].sort().join(", ")}`);
  if (!LOCATION_PRECISIONS.has(locationPrecision))
    throw new Error(`Invalid locationPrecision '${locationPrecision}' — must be one of: ${[...LOCATION_PRECISIONS].sort().join(", ")}`);
  if (!agents.length) throw new Error("At least one agent is required");

  const nowUs = Date.now() * 1000;
  const entry: ExposureEntry = {
    recordType:       "exposure",
    timestampUs:      timestampUs ?? nowUs,
    location,
    agents:           [...agents].map(a => ({ ...a })),
    source,
    measurementType,
    locationPrecision,
    qualityNotes:     [...qualityNotes],
    previousHash,
    entryHash:        "", // placeholder, filled below
  };
  entry.entryHash = await sha256hex(stableStringify({ ...entry, entryHash: "" }));
  return entry;
}

export function validateExposureEntry(entry: ExposureEntry): { valid: boolean; errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (entry.recordType !== "exposure") errors.push("recordType must be 'exposure'");
  for (const field of ["timestampUs", "agents", "source", "measurementType",
                       "locationPrecision", "entryHash"]) {
    if (!(field in entry) || entry[field as keyof ExposureEntry] == null) {
      errors.push(`Missing required field: ${field}`);
    }
  }

  if (entry.source && !EXPOSURE_SOURCES.has(entry.source))
    errors.push(`Invalid source '${entry.source}'`);
  if (entry.measurementType && !EXPOSURE_MEASUREMENT_TYPES.has(entry.measurementType))
    errors.push(`Invalid measurementType '${entry.measurementType}'`);
  if (entry.locationPrecision && !LOCATION_PRECISIONS.has(entry.locationPrecision))
    errors.push(`Invalid locationPrecision '${entry.locationPrecision}'`);

  if (!entry.agents.length) errors.push("No agents present");
  else {
    for (let i = 0; i < entry.agents.length; i++) {
      const a = entry.agents[i];
      if (a.agentId == null) errors.push(`Agent ${i}: missing agentId`);
      if (a.value == null) errors.push(`Agent ${i}: missing value`);
      else if (a.value < 0) errors.push(`Agent ${i} (${a.agentId}): negative value`);
    }
  }

  const computed = entryHash(entry as ExposureEntry);
  if (entry.entryHash !== computed) {
    errors.push(`Entry hash mismatch — entry may be tampered`);
  }

  return { valid: errors.length === 0, errors, warnings };
}

export function validateExposureChain(entries: ExposureEntry[]): ExposureChainResult {
  const errors: string[] = [];
  let firstBroken: number | null = null;

  if (!entries.length) {
    return { valid: false, errors: ["Chain is empty"], firstBrokenIndex: 0, entryCount: 0 };
  }

  for (let i = 0; i < entries.length; i++) {
    const result = validateExposureEntry(entries[i]);
    if (!result.valid) {
      errors.push(`Entry ${i}: ${result.errors.join("; ")}`);
      if (firstBroken == null) firstBroken = i;
      continue;
    }

    if (i === 0) {
      if (entries[i].previousHash !== null) {
        errors.push(`Entry ${i}: genesis entry must have previousHash: null`);
        if (firstBroken == null) firstBroken = i;
      }
    } else {
      if (entries[i].previousHash !== entries[i - 1].entryHash) {
        errors.push(`Entry ${i}: previousHash does not match entry ${i - 1} entryHash`);
        if (firstBroken == null) firstBroken = i;
      }
    }
  }

  return {
    valid: errors.length === 0 && firstBroken == null,
    errors,
    firstBrokenIndex: firstBroken,
    entryCount: entries.length,
  };
}

/**
 * Append an exposure entry to a .bxp.json ledger file (Node.js only).
 * In the browser, call createExposureEntry() and store via IndexedDB instead.
 */
export async function appendToLedger(
  ledgerPath: string,
  newEntry: Partial<ExposureEntry> & { agents: AgentReading[] },
): Promise<{ valid: boolean; entry?: ExposureEntry; errors: string[]; ledgerPath: string }> {
  // Browser-safe: no fs available. Return the entry for caller to store.
  let fs: any;
  try { fs = require("fs"); } catch { fs = null; }

  let entries: ExposureEntry[] = [];
  if (fs && fs.existsSync(ledgerPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(ledgerPath, "utf-8"));
      entries = Array.isArray(data) ? data : (data.entries ?? []);
      const chain = validateExposureChain(entries);
      if (!chain.valid) {
        return { valid: false, errors: [`Existing ledger chain invalid: ${chain.errors[0]}`], ledgerPath };
      }
    } catch (e) {
      return { valid: false, errors: [`Cannot read ledger: ${e}`], ledgerPath };
    }
  }

  const previousHash = entries.length ? entries[entries.length - 1].entryHash : null;
  const entry = await createExposureEntry(newEntry.agents, {
    source: newEntry.source ?? "manual",
    measurementType: newEntry.measurementType ?? "manual",
    location: newEntry.location,
    previousHash,
    locationPrecision: newEntry.locationPrecision ?? "area",
    qualityNotes: newEntry.qualityNotes,
    timestampUs: newEntry.timestampUs,
  });

  entries.push(entry);

  if (fs) {
    const tmp = ledgerPath + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify(entries, null, 2));
    fs.renameSync(tmp, ledgerPath);
  }

  return { valid: true, entry, errors: [], ledgerPath };
}

/**
 * Read and validate a .bxp.json ledger file (Node.js only).
 * Browser callers should use IndexedDB + validateExposureChain().
 */
export function readLedger(ledgerPath: string): {
  valid: boolean; entries: ExposureEntry[]; errors: string[];
  entryCount: number; chainValid: boolean;
} {
  let fs: any;
  try { fs = require("fs"); } catch { fs = null; }

  if (!fs || !fs.existsSync(ledgerPath)) {
    return { valid: false, errors: [`Ledger not found: ${ledgerPath}`], entries: [], entryCount: 0, chainValid: false };
  }

  let data: unknown;
  try { data = JSON.parse(fs.readFileSync(ledgerPath, "utf-8")); }
  catch (e) { return { valid: false, errors: [`Cannot parse ledger: ${e}`], entries: [], entryCount: 0, chainValid: false }; }

  const entries: ExposureEntry[] = Array.isArray(data) ? data : (data as any).entries ?? [];
  const chain = validateExposureChain(entries);

  return {
    valid: chain.valid,
    entries,
    errors: chain.errors,
    entryCount: entries.length,
    chainValid: chain.valid,
  };
}

// ─── Default export ───────────────────────────────────────────

export default BXPClient;
export * from './bxp-binary.js';
