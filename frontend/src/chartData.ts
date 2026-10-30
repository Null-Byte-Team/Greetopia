/** Pure helpers for the charts (no React) so the maths is easy to reason about. */
export type Row = { metric?: string; value: number; received_at: string };

export function vpdKpa(tempC: number | null | undefined, rh: number | null | undefined): number | null {
  if (tempC == null || rh == null || !isFinite(tempC) || !isFinite(rh) || rh < 0 || rh > 100 || tempC < -40 || tempC > 85) return null;
  const svp = 0.6108 * Math.exp((17.27 * tempC) / (tempC + 237.3));
  return Math.round(svp * (1 - rh / 100) * 100) / 100;
}

/** Merge per-metric series onto minute buckets. Missing values stay null: nothing is interpolated or invented. */
export function mergeSeries(series: Record<string, Row[]>, lang: string): any[] {
  const buckets = new Map<number, any>();
  for (const [name, rows] of Object.entries(series)) {
    for (const r of rows) {
      const t = Math.floor(new Date(r.received_at).getTime() / 60000) * 60000;
      const b = buckets.get(t) || { t };
      b[name] = r.value;
      buckets.set(t, b);
    }
  }
  return [...buckets.values()]
    .sort((a, b) => a.t - b.t)
    .map(b => ({ ...b, vpd: vpdKpa(b.temp, b.hum), label: new Date(b.t).toLocaleTimeString(lang === 'ar' ? 'ar-EG' : [], { hour: '2-digit', minute: '2-digit' }) }));
}
