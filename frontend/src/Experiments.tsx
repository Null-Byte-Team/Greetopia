import { FormEvent, useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { Language } from './i18n';
import { useX } from './i18n_extra';

export default function Experiments({ lang, canControl }: { lang: Language; canControl: boolean }) {
  const x = useX(lang);
  const [list, setList] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [results, setResults] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [form, setForm] = useState({ name: '', hypothesis: '', plants: '', control: 'fixed_schedule', seed: 42 });

  const refresh = useCallback(async () => {
    try { setList(await api.experiments()); } catch (e: any) { setMessage(e.message); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const open = async (key: string) => {
    setSelected(key); setResults(null); setMessage('');
    try { setResults(await api.experimentResults(key)); } catch (e: any) { setMessage(e.message); }
  };
  const act = async (fn: () => Promise<any>) => {
    try { await fn(); setMessage(x('saved')); await refresh(); if (selected) await open(selected); } catch (e: any) { setMessage(e.message); }
  };
  const create = (ev: FormEvent) => {
    ev.preventDefault();
    act(() => api.createExperiment({ name: form.name, hypothesis: form.hypothesis, plant_ids: form.plants.split(',').map(s => s.trim()).filter(Boolean), arms: ['adaptive', form.control], seed: Number(form.seed) }));
  };

  return (
    <div className="insights">
      <section className="panel ix-card"><div className="panel-head"><h3>{x('experiments')}</h3></div>
        {message && <p role="status" className="muted-note">{message}</p>}
        <table className="ix-table"><tbody>
          {list.map(e => (
            <tr key={e.key}><td><button className="small-outline" onClick={() => open(e.key)}>{e.name}</button></td><td>{e.status}</td><td>{x('exp_origin')}: {e.data_origin}</td>
              <td>{canControl && e.status === 'draft' && <button onClick={() => act(() => api.startExperiment(e.key))}>{x('exp_start')}</button>}
                {canControl && e.status === 'running' && <button onClick={() => act(() => api.stopExperiment(e.key))}>{x('exp_stop')}</button>}</td></tr>))}
          {list.length === 0 && <tr><td>{x('no_data')}</td></tr>}
        </tbody></table>
      </section>

      {canControl && (
        <section className="panel ix-card"><div className="panel-head"><h3>{x('exp_new')}</h3></div>
          <form onSubmit={create} className="ix-form">
            <label>{x('exp_name')}<input required minLength={3} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
            <label>{x('exp_hyp')}<textarea required minLength={10} value={form.hypothesis} onChange={e => setForm({ ...form, hypothesis: e.target.value })} /></label>
            <label>{x('exp_plants')}<input required value={form.plants} onChange={e => setForm({ ...form, plants: e.target.value })} placeholder="plant01, plant02, plant03, plant04" /></label>
            <label>{x('exp_control')}<select value={form.control} onChange={e => setForm({ ...form, control: e.target.value })}><option value="fixed_schedule">fixed_schedule</option><option value="fixed_threshold">fixed_threshold</option></select></label>
            <label>{x('exp_seed')}<input type="number" min={0} value={form.seed} onChange={e => setForm({ ...form, seed: Number(e.target.value) })} /></label>
            <button type="submit">{x('exp_create')}</button>
          </form>
        </section>)}

      {results && (
        <section className="panel ix-card"><div className="panel-head"><h3>{x('exp_results')}: {results.experiment.name}</h3></div>
          <p><b>{x('exp_origin')}: {results.label}</b></p>
          <p><small>{results.experiment.hypothesis}</small></p>
          <table className="ix-table"><thead><tr><th>{x('arm')}</th><th>{x('metric')}</th><th>{x('n')}</th><th>{x('p_value')}</th><th>{x('effect')}</th></tr></thead>
            <tbody>{results.comparisons.map((c: any, i: number) => (
              <tr key={i}><td>adaptive vs {c.adaptive_vs}</td><td>{c.label}</td><td>{c.test.n1} / {c.test.n2}</td><td>{c.test.p_value ?? '–'}</td><td>{c.test.rank_biserial ?? '–'}</td></tr>))}</tbody></table>
          {results.comparisons.some((c: any) => c.test.p_value == null) && <p className="muted-note">{x('exp_small_n')}</p>}
          <button onClick={() => act(() => api.downloadExperiment(results.experiment.key))}>{x('exp_export')}</button>
        </section>)}
    </div>
  );
}
