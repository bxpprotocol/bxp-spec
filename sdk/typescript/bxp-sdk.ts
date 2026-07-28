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

const RISK_LEVELS: Array<[number, number, string, string, string, string]> = [
  [0,  20,  'CLEAN',     '#00C851', 'No health risk.',           'Enjoy outdoor activities freely.'],
  [21, 40,  'MODERATE',  '#FFBB33', 'Acceptable for most.',      'Sensitive groups: limit prolonged exertion.'],
  [41, 60,  'ELEVATED',  '#FF8800', 'Reduce outdoor exertion.',  'Sensitive groups: avoid outdoor exertion.'],
  [61, 75,  'HIGH',      '#CC0000', 'Wear N95 outdoors.',        'Sensitive groups: stay indoors.'],
  [76, 90,  'VERY_HIGH', '#9B0000', 'Avoid all outdoor activity.', 'Everyone: stay indoors.'],
  [91, 100, 'HAZARDOUS', '#4A0000', 'Emergency. Stay indoors.',  'Evacuate to cleaner air.'],
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
  let level = 'CLEAN', color = '#00C851', advice = 'No health risk.', sadv = 'Enjoy outdoor activities freely.';
  for (const [lo, hi, ln, lc, la, lsa] of RISK_LEVELS) {
    if (score >= lo && score <= hi) {
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
}

// ─── Default export ───────────────────────────────────────────

export default BXPClient;
