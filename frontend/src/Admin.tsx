import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { Language } from './i18n';
import { useX } from './i18n_extra';

export default function Admin({ lang, isAdmin }: { lang: Language; isAdmin: boolean }) {
  const x = useX(lang);
  const [users, setUsers] = useState<any[]>([]);
  const [message, setMessage] = useState('');
  const load = useCallback(async () => { try { setUsers(await api.users()); } catch (e: any) { setMessage(e.message); } }, []);
  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);
  if (!isAdmin) return <div className="panel" role="note">{x('admin_only')}</div>;
  const change = async (id: number, role: string) => { try { await api.setRole(id, role); setMessage(x('saved')); await load(); } catch (e: any) { setMessage(e.message); } };
  return (
    <section className="panel ix-card"><div className="panel-head"><h3>{x('users')}</h3></div>
      {message && <p role="status" className="muted-note">{message}</p>}
      <table className="ix-table"><thead><tr><th>{x('email')}</th><th>{x('role')}</th></tr></thead>
        <tbody>{users.map(u => (
          <tr key={u.id}><td>{u.email}</td><td><select aria-label={`${x('role')} ${u.email}`} value={u.role} onChange={e => change(u.id, e.target.value)}>
            <option value="viewer">viewer</option><option value="operator">operator</option><option value="admin">admin</option></select></td></tr>))}</tbody></table>
    </section>
  );
}
