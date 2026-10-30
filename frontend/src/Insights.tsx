import { useCallback, useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from './api';
import { mergeSeries } from './chartData';
import { Language } from './i18n';
import { useX } from './i18n_extra';

type Props = { plantId: string; lang: Language };

function Box({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <section className="panel ix-card">
      <div className="panel-head"><h3>{title}</h3></div>
      {children}
      {note && <small className="muted-note">{note}</small>}
    </section>
  );
}

function Unavailable({ data, x }: { data: any; x: (k: any) => string }) {
  return <p className="muted-note" role="status"><b>{x('unavailable')}.</b> {x('why')}: {data?.reason || x('no_data')}</p>;
}

const COLORS = { surface: '#7aa87d', mid: '#3e8a5c', root: '#1f5a3c', temp: '#d1783a', hum: '#3b78b5', vpd: '#8a5cb5' };

export default function Insights({ plantId, lang }: Props) {
  const x = useX(lang);
  const [days, setDays] = useState(7);
  const [data, setData] = useState<any>({});
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');

  const load = useCallback(async () => {
    setState('loading');
    const calls: Record<string, Promise<any>> = {
      summary: api.insights(plantId, days), weekly: api.weekly(plantId, lang), growth: api.growth(plantId, Math.max(days, 14)),
      events: api.events(plantId), decisions: api.decisions(plantId), alerts: api.alerts(plantId), ml: api.mlStatus(plantId),
      surface: api.series(plantId, 'soil_surface'), mid: api.series(plantId, 'soil_mid'), root: api.series(plantId, 'soil_root'),
      temp: api.series(plantId, 'temperature_c'), hum: api.series(plantId, 'humidity_pct'),
    };
    const keys = Object.keys(calls);
    const results = await Promise.allSettled(Object.values(calls));
    const next: any = {};
    let failed = 0;
    results.forEach((r, i) => { if (r.status === 'fulfilled') next[keys[i]] = r.value; else failed++; });
    setData(next);
    setState(failed === keys.length ? 'error' : 'ready');
  }, [plantId, days, lang]);

  useEffect(() => { load(); }, [load]);

  const chart = mergeSeries({ surface: data.surface || [], mid: data.mid || [], root: data.root || [], temp: data.temp || [], hum: data.hum || [] }, lang);
  const s = data.summary;
  const root = s?.kpis?.depths?.root;

  if (state === 'loading' && !data.summary) return <div className="loading-indicator">{x('loading')}</div>;
  if (state === 'error') return <div role="alert" className="panel">{x('no_data')} <button onClick={load}>{x('retry')}</button></div>;

  return (
    <div className="insights" aria-live="polite">
      <div className="ix-toolbar">
        <label>{x('window_days')}{' '}
          <select value={days} onChange={e => setDays(Number(e.target.value))} aria-label={x('window_days')}>
            {[1, 7, 14, 30].map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <small>{x('derived_note')}</small>
      </div>

      <div className="insights-grid">
        <Box title={x('soil_by_depth')}>
          {chart.length === 0 ? <p className="muted-note">{x('no_data')}</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" minTickGap={40} /><YAxis domain={[0, 100]} /><Tooltip /><Legend />
                <Line type="monotone" dataKey="surface" stroke={COLORS.surface} dot={false} connectNulls={false} />
                <Line type="monotone" dataKey="mid" stroke={COLORS.mid} dot={false} connectNulls={false} />
                <Line type="monotone" dataKey="root" stroke={COLORS.root} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>)}
        </Box>
        <Box title={x('temp_hum')}>
          {chart.length === 0 ? <p className="muted-note">{x('no_data')}</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" minTickGap={40} /><YAxis yAxisId="t" /><YAxis yAxisId="h" orientation="right" domain={[0, 100]} /><Tooltip /><Legend />
                <Line yAxisId="t" type="monotone" dataKey="temp" stroke={COLORS.temp} dot={false} />
                <Line yAxisId="h" type="monotone" dataKey="hum" stroke={COLORS.hum} dot={false} />
              </LineChart>
            </ResponsiveContainer>)}
        </Box>
        <Box title={x('vpd_hist')}>
          {chart.length === 0 ? <p className="muted-note">{x('no_data')}</p> : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" minTickGap={40} /><YAxis /><Tooltip /><Line type="monotone" dataKey="vpd" stroke={COLORS.vpd} dot={false} /></LineChart>
            </ResponsiveContainer>)}
        </Box>
        <Box title={x('events')}>
          {(data.events || []).length === 0 ? <p className="muted-note">{x('no_data')}</p> : (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={[...(data.events || [])].reverse().map((e: any) => ({ id: `#${e.id}`, requested: e.duration_seconds || 0, observed: e.observed_start_at && e.observed_end_at ? Math.round((new Date(e.observed_end_at).getTime() - new Date(e.observed_start_at).getTime()) / 1000) : 0 }))}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="id" /><YAxis /><Tooltip /><Legend />
                  <Bar dataKey="requested" name={x('requested_s')} fill="#9bbf9e" /><Bar dataKey="observed" name={x('observed_s')} fill="#1f5a3c" />
                </BarChart>
              </ResponsiveContainer>
              <ul className="ix-list">{data.events.slice(0, 5).map((e: any) => <li key={e.id}>#{e.id} · {e.source} · {e.status} · {new Date(e.created_at).toLocaleString(lang === 'ar' ? 'ar-EG' : [])}</li>)}</ul>
            </>)}
        </Box>

        <Box title={x('kpis')} note={x('derived_note')}>
          {!root?.available ? <Unavailable data={root} x={x} /> : (
            <dl className="ix-kv">
              <dt>{x('in_range')}</dt><dd>{root.time_in_range_pct}%</dd><dt>{x('below_min')}</dt><dd>{root.below_min_hours}</dd>
              <dt>{x('stress_integral')}</dt><dd>{root.stress_integral_pct_hours}</dd><dt>{x('saturation')}</dt><dd>{root.saturation_hours}</dd>
              <dt>{x('std')}</dt><dd>{root.std}</dd><dt>{x('covered')}</dt><dd>{root.covered_hours}</dd>
            </dl>)}
        </Box>
        <Box title={x('response')}>
          {!s?.response?.available ? <Unavailable data={s?.response} x={x} /> : (
            <>
              <table className="ix-table"><thead><tr><th>{x('probe')}</th><th>{x('response_rate')}</th><th>{x('gain')}</th><th>{x('delay')}</th></tr></thead>
                <tbody>{Object.entries<any>(s.response.aggregate).map(([k, v]) => <tr key={k}><td>{k}</td><td>{Math.round(v.response_rate * 100)}%</td><td>{v.median_gain ?? '–'}</td><td>{v.median_delay_s ?? '–'}</td></tr>)}</tbody></table>
              {s.response.hypotheses?.length > 0 && <><b>{x('hypotheses')}</b><ul className="ix-list">{s.response.hypotheses.map((h: string) => <li key={h}>{h}</li>)}</ul></>}
            </>)}
        </Box>
        <Box title={x('microclimate')}>
          {!s?.microclimate?.available ? <Unavailable data={s?.microclimate} x={x} /> : (
            <dl className="ix-kv"><dt>{x('heat_hours')}</dt><dd>{s.microclimate.heat_stress_hours}</dd><dt>{x('vpd_high')}</dt><dd>{s.microclimate.high_vpd_hours}</dd>
              <dt>{x('vpd_low')}</dt><dd>{s.microclimate.low_vpd_hours}</dd><dt>{x('fungal')}</dt><dd>{s.microclimate.fungal_risk_index}/100</dd></dl>)}
        </Box>
        <Box title={x('integrity')}>
          {s?.integrity?.suspect_now && <p role="alert" className="muted-note"><b>{x('suspect')}:</b> {s.integrity.suspect_now}</p>}
          <table className="ix-table"><thead><tr><th>{x('probe')}</th><th>{x('score')}</th><th>{x('why')}</th></tr></thead>
            <tbody>{Object.entries<any>(s?.integrity?.probes || {}).map(([k, p]) => <tr key={k}><td>{k}</td><td>{p.available ? `${p.score}/100` : x('unavailable')}</td><td>{p.available ? (p.reasons || []).join('; ') || '–' : p.reason}</td></tr>)}</tbody></table>
          <small>{x('connectivity')}: {s?.integrity?.connectivity?.available ? `${s.integrity.connectivity.score}/100` : x('unavailable')}</small>
        </Box>
        <Box title={x('pump_health')}>
          {!s?.pump_health?.available ? <Unavailable data={s?.pump_health} x={x} /> : (
            <>
              <dl className="ix-kv"><dt>{x('commands')}</dt><dd>{s.pump_health.commands}</dd><dt>{x('confirmed')}</dt><dd>{s.pump_health.confirmed}</dd><dt>{x('unconfirmed')}</dt><dd>{s.pump_health.unconfirmed}</dd></dl>
              {s.pump_health.flags.length > 0 && <><b>{x('flags')}</b><ul className="ix-list">{s.pump_health.flags.map((f: string) => <li key={f}>{f}</li>)}</ul></>}
            </>)}
        </Box>
        <Box title={x('demand')}>
          {!s?.demand?.available ? <Unavailable data={s?.demand} x={x} /> : s.demand.forecast?.available
            ? <p>{x('hours_to_min')}: <b>{s.demand.forecast.hours_to_min} h</b> ({s.demand.forecast.hours_range_95?.[0]}–{s.demand.forecast.hours_range_95?.[1] ?? '∞'})</p>
            : <Unavailable data={s.demand.forecast} x={x} />}
        </Box>
        <Box title={x('ml')}>
          {data.ml?.prediction?.status === 'ok' ? <p>{x('ml_prob')}: <b>{Math.round(data.ml.prediction.stress_probability * 100)}%</b></p> : <Unavailable data={data.ml?.prediction} x={x} />}
        </Box>
        <Box title={x('growth')}>
          {!data.growth?.available ? <Unavailable data={data.growth} x={x} /> : (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={data.growth.points.map((p: any) => ({ label: new Date(p.received_at).toLocaleDateString(lang === 'ar' ? 'ar-EG' : []), green: p.green_fraction }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" minTickGap={30} /><YAxis /><Tooltip /><Line type="monotone" dataKey="green" stroke="#3e8a5c" dot={false} /></LineChart>
            </ResponsiveContainer>)}
        </Box>
        <Box title={x('decisions')}>
          {(data.decisions || []).length === 0 ? <p className="muted-note">{x('no_data')}</p> : (
            <ul className="ix-list">{data.decisions.slice(0, 6).map((d: any) => <li key={d.id}><b>{d.decision}</b> · {d.source} · {new Date(d.created_at).toLocaleString(lang === 'ar' ? 'ar-EG' : [])}<br /><small>{d.reason}</small></li>)}</ul>)}
        </Box>
        <Box title={x('alerts')}>
          {(data.alerts || []).length === 0 ? <p className="muted-note">{x('no_data')}</p> : (
            <ul className="ix-list">{data.alerts.map((a: any) => <li key={a.id}><b>{a.severity}</b> · {a.kind}<br /><small>{a.message}</small></li>)}</ul>)}
        </Box>
        <Box title={data.weekly?.title || x('weekly')}>
          {data.weekly ? <><ul className="ix-list">{data.weekly.lines.map((l: string) => <li key={l}>{l}</li>)}</ul><small>{data.weekly.source}</small></> : <p className="muted-note">{x('no_data')}</p>}
        </Box>
      </div>
    </div>
  );
}
