import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, Droplets, Leaf, Thermometer, Wind, CloudRain, Camera, ShieldCheck,
  CircleAlert, RefreshCw, Send, Sprout, ChevronDown, Zap, Clock3, Settings2,
  Plus, History, CheckCircle2, Download, Smartphone, Apple, X, ExternalLink,
  Sun, Moon, Languages, LogOut
} from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, UNAUTHORIZED_EVENT, apiConfigError, API_ORIGIN } from './api';
import { translations, Language, Theme } from './i18n';
import SignInPage from './SignInPage';

type Plant = {
  plant_id: string;
  name: string;
  species: string;
  species_source?: string;
  growth_stage: string;
  mode: 'auto' | 'manual';
  ideal_moisture_min: number;
  ideal_moisture_max: number;
};

function MetricCard({
  icon: Icon,
  label,
  value,
  unit,
  sub,
  kind = 'normal'
}: {
  icon: any;
  label: string;
  value: string | number;
  unit?: string;
  sub?: string;
  kind?: string;
}) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <span className={`metric-icon ${kind}`}>
          <Icon size={17} />
        </span>
      </div>
      <div className="metric-value">
        {value}
        <small>{unit}</small>
      </div>
      <div className="metric-sub">{sub || 'Waiting for sensor data'}</div>
    </div>
  );
}

function App() {
  // Theme & Language State with persistence
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('greetopia_theme') as Theme | null;
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  const [lang, setLang] = useState<Language>(() => {
    const saved = localStorage.getItem('greetopia_lang') as Language | null;
    if (saved === 'en' || saved === 'ar') return saved;
    return navigator.language.startsWith('ar') ? 'ar' : 'en';
  });

  const t = useMemo(() => translations[lang], [lang]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('greetopia_theme', theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', lang);
    localStorage.setItem('greetopia_lang', lang);
  }, [lang]);

  const toggleTheme = () => setTheme(prev => (prev === 'dark' ? 'light' : 'dark'));
  const toggleLang = () => setLang(prev => (prev === 'en' ? 'ar' : 'en'));

  // User Auth State
  const [user, setUser] = useState<any>(() => {
    try {
      const raw = localStorage.getItem('greetopia_user');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const [forceShowSignIn, setForceShowSignIn] = useState(false);

  useEffect(() => {
    const onUnauthorized = () => {
      localStorage.removeItem('greetopia_token');
      localStorage.removeItem('greetopia_user');
      setUser(null);
      setForceShowSignIn(true);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    const token = localStorage.getItem('greetopia_token');
    if (token) {
      api.authMe()
        .then(u => {
          setUser(u);
          localStorage.setItem('greetopia_user', JSON.stringify(u));
          localStorage.setItem('greetopia_remember', 'true');
        })
        .catch(err => {
          // Keep cached user session! Never wipe login state on cold boot or network hiccups.
          console.warn('Background session refresh notice:', err);
        });
    }
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const handleAuth = (token: string, authedUser: any) => {
    localStorage.setItem('greetopia_token', token);
    localStorage.setItem('greetopia_user', JSON.stringify(authedUser));
    localStorage.setItem('greetopia_remember', 'true');
    setUser(authedUser);
    setForceShowSignIn(false);
    load();
  };

  const handleSignOut = () => {
    localStorage.removeItem('greetopia_token');
    localStorage.removeItem('greetopia_user');
    localStorage.removeItem('greetopia_remember');
    setUser(null);
    setShowUserDropdown(false);
    setForceShowSignIn(true);
  };

  // Core App State
  const [showDownloads, setShowDownloads] = useState(false);
  const [deferredInstall, setDeferredInstall] = useState<any>(null);
  const [plants, setPlants] = useState<Plant[]>([]);
  const [systemHealth, setSystemHealth] = useState<any>(null);
  const [plantId, setPlantId] = useState('plant01');
  const [overview, setOverview] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [seconds, setSeconds] = useState(5);
  const [chatText, setChatText] = useState('');
  const [chatAnswer, setChatAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newPlant, setNewPlant] = useState({
    plant_id: '',
    name: '',
    species: '',
    growth_stage: 'Seedling',
    ideal_moisture_min: 30,
    ideal_moisture_max: 65,
    light_needs: '',
    notes: ''
  });
  const [diary, setDiary] = useState<any[]>([]);
  const [speciesEdit, setSpeciesEdit] = useState('');
  const [speciesSuggestions, setSpeciesSuggestions] = useState<any[]>([]);

  const load = useCallback(async () => {
    setError('');
    try {
      const [p, hz] = await Promise.all([api.plants(), api.health()]);
      setPlants(p);
      setSystemHealth(hz);
      const chosen = p.some(x => x.plant_id === plantId) ? plantId : (p[0]?.plant_id || 'plant01');
      if (chosen !== plantId) setPlantId(chosen);
      const [o, h, d, di] = await Promise.all([
        api.overview(chosen),
        api.history(chosen),
        api.decisions(chosen),
        api.diary(chosen)
      ]);
      setOverview(o);
      setHistory(h);
      setDecisions(d);
      setDiary(di);
    } catch (e: any) {
      setError(e.message || 'Could not reach the backend.');
    } finally {
      setLoading(false);
    }
  }, [plantId]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const handler = (event: Event) => {
      event.preventDefault();
      setDeferredInstall(event);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const androidDownload = (import.meta.env.VITE_ANDROID_DOWNLOAD_URL as string | undefined) || '/downloads/greetopia.apk';
  const iosDownload = import.meta.env.VITE_IOS_DOWNLOAD_URL as string | undefined;

  const installPwa = async () => {
    if (!deferredInstall) return;
    await deferredInstall.prompt();
    setDeferredInstall(null);
  };

  const selected = plants.find(p => p.plant_id === plantId) || overview?.plant;
  const readings = overview?.readings || {};

  useEffect(() => {
    setSpeciesEdit(selected?.species || '');
  }, [selected?.species, plantId]);

  useEffect(() => {
    const q = speciesEdit.trim();
    if (q.length < 2) {
      setSpeciesSuggestions([]);
      return;
    }
    let active = true;
    const timer = setTimeout(() => {
      api.plantKnowledge(q)
        .then(r => {
          if (active) setSpeciesSuggestions(r.results || []);
        })
        .catch(() => {
          if (active) setSpeciesSuggestions([]);
        });
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [speciesEdit]);

  const metric = (key: string) => readings[key];
  const display = (key: string, digits = 0) => {
    const m = metric(key);
    return m && m.fresh ? Number(m.value).toFixed(digits) : '--';
  };

  const chartData = useMemo(() => {
    const relevant = history.filter(x => ['soil_surface', 'soil_mid', 'soil_root'].includes(x.metric));
    return relevant
      .reduce((acc: any, row: any) => {
        const time = new Date(row.received_at).toLocaleTimeString(lang === 'ar' ? 'ar-EG' : [], {
          hour: '2-digit',
          minute: '2-digit'
        });
        let entry = acc.find((x: any) => x.time === time);
        if (!entry) {
          entry = { time };
          acc.push(entry);
        }
        entry[row.metric] = Number(row.value);
        return acc;
      }, [])
      .slice(-24);
  }, [history, lang]);

  const changeMode = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const mode = selected.mode === 'auto' ? 'manual' : 'auto';
      await api.mode(plantId, mode);
      const modeLabel = lang === 'ar' ? (mode === 'auto' ? 'التلقائي' : 'اليدوي') : mode.toUpperCase();
      setActionMessage(`${t.mode_changed} ${modeLabel}.`);
      await load();
    } catch (e: any) {
      setActionMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const water = async () => {
    setBusy(true);
    setActionMessage('');
    try {
      const r = await api.water(plantId, seconds);
      setActionMessage(r.published ? `${t.water_queued} ${seconds}s. ${t.cmd_published_waiting}.` : `${t.water_not_sent}: ${r.message}`);
    } catch (e: any) {
      setActionMessage(e.message);
    } finally {
      setBusy(false);
      load();
    }
  };

  const runDecision = async () => {
    setBusy(true);
    try {
      const r = await api.decision(plantId);
      setActionMessage(`${t.decision_prefix}: ${r.decision.toUpperCase()} · ${r.reason}`);
      await load();
    } catch (e: any) {
      setActionMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const sendChat = async (e: any) => {
    e.preventDefault();
    if (!chatText.trim()) return;
    setBusy(true);
    try {
      const r = await api.chat(plantId, chatText);
      setChatAnswer(r.answer);
      setChatText('');
    } catch (err: any) {
      setChatAnswer(err.message);
    } finally {
      setBusy(false);
    }
  };

  const addPlant = async (e: any) => {
    e.preventDefault();
    setBusy(true);
    try {
      const p = await api.createPlant(newPlant);
      setShowAdd(false);
      setPlantId(p.plant_id);
      setNewPlant({
        plant_id: '',
        name: '',
        species: '',
        growth_stage: 'Seedling',
        ideal_moisture_min: 30,
        ideal_moisture_max: 65,
        light_needs: '',
        notes: ''
      });
      setActionMessage(t.plant_profile_created);
      setLoading(true);
      setTimeout(load, 100);
    } catch (err: any) {
      setActionMessage(err.message);
    } finally {
      setBusy(false);
    }
  };

  const saveSpecies = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const p = await api.updatePlant(plantId, { species: speciesEdit.trim() });
      setActionMessage(p.species ? `${t.species_saved_prefix} ${p.species}.` : t.species_cleared);
      await load();
    } catch (e: any) {
      setActionMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const analyzePhoto = async () => {
    setBusy(true);
    try {
      const r = await api.analyzePhoto(plantId);
      const guess = r.vision?.common_name || r.vision?.species_guess || 'uncertain';
      setActionMessage(`${t.photo_analyzed_prefix} ${guess}.`);
      await load();
    } catch (e: any) {
      setActionMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const generateDiary = async () => {
    setBusy(true);
    try {
      await api.generateDiary(plantId);
      setDiary(await api.diary(plantId));
      setActionMessage(t.diary_generated);
    } catch (e: any) {
      setActionMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const canControl = user?.role === 'operator' || user?.role === 'admin';
  const device = overview?.device;
  const deviceLabel = device?.state === 'online' ? t.device_online : device?.state === 'stale' ? t.device_stale : t.device_offline;
  const lastEvent = overview?.last_event;
  const candidateSpecies = overview?.photo?.vision?.species_guess || overview?.photo?.vision?.common_name;

  const useSuggestedSpecies = async () => {
    if (!candidateSpecies) return;
    setBusy(true);
    try {
      await api.updatePlant(plantId, { species: String(candidateSpecies) });
      setActionMessage(`${t.species_saved_prefix} ${candidateSpecies}.`);
      await load();
    } catch (e: any) {
      setActionMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const lastSeen = metric('soil_root')?.received_at
    ? new Date(metric('soil_root').received_at).toLocaleString(lang === 'ar' ? 'ar-EG' : [])
    : t.no_telemetry_received;

  if (apiConfigError) {
    return <div role="alert" style={{ padding: 24 }}>{apiConfigError}</div>;
  }

  if (forceShowSignIn || !user) {
    return (
      <SignInPage
        t={t}
        theme={theme}
        lang={lang}
        onAuth={handleAuth}
        toggleTheme={toggleTheme}
        toggleLang={toggleLang}
      />
    );
  }

  return (
    <div className="app-shell">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Sprout size={23} />
          </div>
          <div>
            <strong>{t.brand_name}</strong>
            <span>{t.brand_sub}</span>
          </div>
        </div>

        <div className="workspace-label">{t.workspace}</div>
        <button className="nav-item active">
          <Activity size={17} /> {t.nav_overview} <span className="nav-dot" />
        </button>
        <button className="nav-item" onClick={() => document.getElementById('plant-profile')?.scrollIntoView({ behavior: 'smooth' })}>
          <Leaf size={17} /> {t.nav_profiles}
        </button>
        <button className="nav-item" onClick={() => document.getElementById('history')?.scrollIntoView({ behavior: 'smooth' })}>
          <History size={17} /> {t.nav_history}
        </button>
        <button className="nav-item" onClick={() => document.getElementById('plant-diary')?.scrollIntoView({ behavior: 'smooth' })}>
          <Clock3 size={17} /> {t.nav_diary}
        </button>

        <div className="sidebar-bottom">
          <div className="system-status">
            <span className="status-pulse" />
            <div>
              <b>{t.system_status}</b>
              <small>{error ? t.api_unavailable : t.local_dashboard}</small>
            </div>
          </div>
          <div className="sidebar-foot">{t.version}</div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">{t.topbar_eyebrow}</div>
            <h1>
              {t.topbar_h1} <em>{t.topbar_em}</em>
            </h1>
          </div>

          <div className="top-actions">
            {/* Theme Toggle Button */}
            <button
              className="pill-toggle-btn"
              onClick={toggleTheme}
              title={theme === 'dark' ? t.theme_toggle_to_light : t.theme_toggle_to_dark}
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              <span>{theme === 'dark' ? (lang === 'ar' ? 'فاتح' : 'Light') : (lang === 'ar' ? 'داكن' : 'Dark')}</span>
            </button>

            {/* Language Toggle Button */}
            <button
              className="pill-toggle-btn"
              onClick={toggleLang}
              title={t.lang_toggle}
              aria-label="Toggle language"
            >
              <Languages size={15} />
              <span>{t.lang_toggle}</span>
            </button>

            {/* Mobile App Download */}
            <button className="download-app-btn" onClick={() => setShowDownloads(true)}>
              <Download size={15} /> {t.download_app}
            </button>

            {/* Live Data Badge */}
            <div className="live-pill">
              <span /> {t.live_data} <small>{t.refresh_rate}</small>
            </div>

            {/* Manual Refresh */}
            <button
              className="icon-button"
              onClick={() => {
                setLoading(true);
                load();
              }}
              aria-label={t.refresh_label}
            >
              <RefreshCw size={17} />
            </button>

            {user && user.provider !== 'guest' ? (
              <div style={{ position: 'relative' }}>
                <button
                  className="user-avatar-btn"
                  onClick={() => setShowUserDropdown(!showUserDropdown)}
                  aria-label="User profile"
                  type="button"
                >
                  {user.avatar_url ? (
                    <img className="user-avatar-img" src={user.avatar_url} alt={user.name || 'User'} />
                  ) : (
                    <div className="user-avatar-fallback">
                      {user.name ? user.name[0].toUpperCase() : 'U'}
                    </div>
                  )}
                  <span className="user-avatar-name">{user.name || 'User'}</span>
                  <ChevronDown size={13} style={{ opacity: 0.6 }} />
                </button>
                {showUserDropdown && (
                  <div className="user-dropdown">
                    <div className="user-dropdown-header">
                      <strong>{user.name || 'User'}</strong>
                      <small>{user.email}</small>
                    </div>
                    <button className="user-dropdown-item danger" type="button" onClick={handleSignOut}>
                      <LogOut size={14} /> {t.sign_out}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <button
                className="primary-btn"
                style={{ height: 35, padding: '0 12px', fontSize: 11 }}
                type="button"
                onClick={() => setForceShowSignIn(true)}
              >
                {t.btn_signin}
              </button>
            )}
          </div>
        </header>

        {error && (
          <div className="error-banner">
            <CircleAlert size={18} />
            <div>
              <b>{t.error_title}</b>
              <span>{error}. {t.error_desc}</span>
            </div>
            <button onClick={load}>{t.retry}</button>
          </div>
        )}

        {actionMessage && (
          <div className="notice">
            <CheckCircle2 size={17} />
            <span>{actionMessage}</span>
            <button onClick={() => setActionMessage('')}>×</button>
          </div>
        )}

        {/* Hero Section */}
        <section className="plant-hero">
          <div className="hero-text">
            <div className="hero-kicker">
              <span className="green-pip" /> {t.currently_monitoring}
            </div>

            <div className="plant-title-row">
              <h2>{selected?.name || (lang === 'ar' ? 'نباتي' : 'My Plant')}</h2>
              <button className="plant-select" onClick={() => document.getElementById('plant-selector')?.focus()}>
                <select id="plant-selector" value={plantId} onChange={e => setPlantId(e.target.value)}>
                  {plants.map(p => (
                    <option key={p.plant_id} value={p.plant_id}>
                      {p.name} · {p.plant_id}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} />
              </button>
            </div>

            <p className="plant-description">
              {selected?.species || t.species_unconfirmed} <span>·</span> {selected?.growth_stage || t.growth_stage_unset} <span>·</span> ID: {plantId}
            </p>

            <div className="hero-chips">
              <span>
                <span className="chip-dot" />
                {selected?.mode === 'auto'
                  ? (systemHealth?.auto_decisions_enabled ? t.auto_mode_exec : t.auto_mode_locked)
                  : t.manual_control}
              </span>
              <span>
                <Clock3 size={13} /> {t.last_sensor_update}: {lastSeen}
              </span>
              <span title={device?.basis || ''}>
                <CircleAlert size={13} /> {deviceLabel}
              </span>
              {lastEvent && (
                <span>
                  <Droplets size={13} /> {t.last_command}: {lastEvent.status}{lastEvent.duration_seconds ? ` · ${lastEvent.duration_seconds}s` : ''}
                </span>
              )}
            </div>

            <div className="hero-actions">
              <button className="primary-btn" onClick={water} disabled={busy || !canControl}>
                <Droplets size={16} /> {t.water_now}
              </button>
              <button className="secondary-btn" onClick={changeMode} disabled={busy || !canControl}>
                <Settings2 size={16} /> {selected?.mode === 'auto' ? t.switch_to_manual : t.switch_to_auto}
              </button>
              <button className="text-btn" onClick={runDecision} disabled={busy || !canControl}>
                <Zap size={15} /> {t.run_check}
              </button>
            </div>

            {!canControl && <p role="note" className="muted-note">{t.read_only_notice}</p>}

            <div className="duration-control">
              <span>{t.watering_duration}</span>
              <input type="range" min="1" max="15" value={seconds} onChange={e => setSeconds(Number(e.target.value))} />
              <b>{seconds}s</b>
              <small>{t.safety_limit}</small>
            </div>
          </div>

          <div className="hero-art">
            <div className="sun-glow" />
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="plant-illustration">
              <div className="stem" />
              <div className="leaf-shape leaf-a" />
              <div className="leaf-shape leaf-b" />
              <div className="leaf-shape leaf-c" />
              <div className="leaf-shape leaf-d" />
              <div className="pot"><span /></div>
            </div>
            <div className="art-label label-top">
              <span className="label-icon">
                <Droplets size={14} />
              </span>
              <div>
                <small>{t.root_moisture}</small>
                <b>{display('soil_root')}<i>%</i></b>
              </div>
            </div>
            <div className="art-label label-bottom">
              <span className="label-icon mint">
                <Activity size={14} />
              </span>
              <div>
                <small>{t.vpd_index}</small>
                <b>{overview?.vpd_kpa ?? '--'}<i> kPa</i></b>
              </div>
            </div>
          </div>
        </section>

        {/* Section Heading */}
        <div className="section-heading">
          <div>
            <span className="section-overline">{t.sensor_network}</span>
            <h3>{t.env_conditions}</h3>
          </div>
          <span className="freshness">
            <span /> {Object.values(readings).some((x: any) => x.fresh) ? t.receiving_telemetry : t.waiting_telemetry}
          </span>
        </div>

        {/* 6 Metric Cards */}
        <section className="metric-grid">
          <MetricCard
            icon={Droplets}
            label={t.metric_surface}
            value={display('soil_surface')}
            unit="%"
            sub={metric('soil_surface')?.fresh ? t.fresh_reading : t.no_fresh_reading}
            kind="blue"
          />
          <MetricCard
            icon={Droplets}
            label={t.metric_mid}
            value={display('soil_mid')}
            unit="%"
            sub={metric('soil_mid')?.fresh ? t.fresh_reading : t.no_fresh_reading}
            kind="blue"
          />
          <MetricCard
            icon={Sprout}
            label={t.metric_root}
            value={display('soil_root')}
            unit="%"
            sub={metric('soil_root')?.fresh ? t.primary_signal : t.missing_stale}
            kind="green"
          />
          <MetricCard
            icon={Thermometer}
            label={t.metric_temp}
            value={display('temperature_c', 1)}
            unit="°C"
            sub={metric('temperature_c')?.fresh ? t.dht22_label : t.no_fresh_reading}
            kind="orange"
          />
          <MetricCard
            icon={Wind}
            label={t.metric_humidity}
            value={display('humidity_pct')}
            unit="%"
            sub={metric('humidity_pct')?.fresh ? t.dht22_label : t.no_fresh_reading}
            kind="purple"
          />
          <MetricCard
            icon={Activity}
            label={t.metric_leaf_wetness}
            value={display('leaf_wetness_pct')}
            unit="%"
            sub={metric('leaf_wetness_pct')?.fresh ? t.optional_sensor : t.not_implemented}
            kind="gray"
          />
        </section>

        {/* Analytics & Vision */}
        <section className="content-grid">
          <div className="panel chart-panel" id="history">
            <div className="panel-head">
              <div>
                <span className="section-overline">{t.last_readings}</span>
                <h3>{t.soil_trends}</h3>
              </div>
              <span className="mini-tag">
                <span /> {t.sensor_history_tag}
              </span>
            </div>

            <div className="chart-legend">
              <span><i className="legend-surface" /> {t.surface_legend}</span>
              <span><i className="legend-mid" /> {t.mid_legend}</span>
              <span><i className="legend-root" /> {t.root_legend}</span>
            </div>

            <div className="chart-wrap">
              {chartData.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 8, right: 5, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="surfaceFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#8db6d5" stopOpacity={0.24} />
                        <stop offset="100%" stopColor="#8db6d5" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="rootFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#6ca889" stopOpacity={0.25} />
                        <stop offset="100%" stopColor="#6ca889" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 4" vertical={false} stroke={theme === 'dark' ? '#203529' : '#e6e9e4'} />
                    <XAxis dataKey="time" tickLine={false} axisLine={false} tick={{ fill: theme === 'dark' ? '#7a9181' : '#8b958d', fontSize: 10 }} />
                    <YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={{ fill: theme === 'dark' ? '#7a9181' : '#8b958d', fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 12,
                        border: theme === 'dark' ? '1px solid #22382c' : '1px solid #e5e9e3',
                        background: theme === 'dark' ? '#14221a' : '#fff',
                        color: theme === 'dark' ? '#e2ece4' : '#25342c',
                        fontSize: 12
                      }}
                    />
                    <Area type="monotone" dataKey="soil_surface" name={t.surface_legend} stroke="#82aecd" fill="url(#surfaceFill)" connectNulls={false} strokeWidth={2} />
                    <Area type="monotone" dataKey="soil_mid" name={t.mid_legend} stroke="#d5aa6c" fill="transparent" connectNulls={false} strokeWidth={2} />
                    <Area type="monotone" dataKey="soil_root" name={t.root_legend} stroke="#659d7b" fill="url(#rootFill)" connectNulls={false} strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-chart">
                  <Activity size={26} />
                  <b>{t.waiting_first_readings}</b>
                  <span>{t.mqtt_hint}</span>
                </div>
              )}
            </div>

            <div className="chart-foot">
              <span>{t.timestamp_note}</span>
              <span>{history.length} {t.records_loaded}</span>
            </div>
          </div>

          <div className="right-stack">
            {/* Climate Stress */}
            <div className="panel climate-panel">
              <div className="panel-head">
                <div>
                  <span className="section-overline">{t.plant_climate}</span>
                  <h3>{t.stress_indicators}</h3>
                </div>
                <Wind size={18} className="muted-icon" />
              </div>
              <div className="vpd-number">
                {overview?.vpd_kpa ?? '--'} <small>kPa</small>
              </div>
              <div className={`vpd-band ${overview?.vpd_band || 'unavailable'}`}>
                {overview?.vpd_band || 'unavailable'} {t.vpd_band}
              </div>
              <p>{t.vpd_desc}</p>
              <div className="weather-row">
                <div className="weather-icon">
                  <CloudRain size={19} />
                </div>
                <div>
                  <b>
                    {overview?.weather?.available
                      ? overview.weather.rain_probability == null
                        ? t.forecast_available
                        : `${Math.round(overview.weather.rain_probability * 100)}% ${t.rain_probability}`
                      : t.weather_not_configured}
                  </b>
                  <small>
                    {overview?.weather?.available
                      ? `${t.next_forecast_rain}: ${overview.weather.rain_mm ?? '--'} mm`
                      : t.weather_env_hint}
                  </small>
                </div>
              </div>
            </div>

            {/* Vision Camera */}
            <div className="panel photo-panel">
              <div className="panel-head">
                <div>
                  <span className="section-overline">{t.gemini_vision}</span>
                  <h3>{t.latest_photo}</h3>
                </div>
                <Camera size={18} className="muted-icon" />
              </div>

              {overview?.photo?.url ? (
                <img className="plant-photo" src={`${API_ORIGIN}${overview.photo.url}`} alt={t.latest_photo} />
              ) : (
                <div className="photo-placeholder">
                  <Camera size={25} />
                  <b>{t.no_photo_yet}</b>
                  <span>{t.cam_interval}</span>
                </div>
              )}

              <div className="photo-foot">
                <span>
                  {overview?.photo?.received_at
                    ? `${t.captured_prefix} ${new Date(overview.photo.received_at).toLocaleString(lang === 'ar' ? 'ar-EG' : [])}`
                    : t.waiting_cam}
                </span>
                <span className="photo-status">
                  {overview?.photo?.vision ? t.status_analyzed : overview?.photo ? t.status_stored : t.status_awaiting}
                </span>
              </div>

              {overview?.photo && (
                <button className="small-outline" style={{ marginTop: 10 }} onClick={analyzePhoto} disabled={busy || !canControl}>
                  <Zap size={13} /> {t.analyze_photo_btn}
                </button>
              )}

              {overview?.photo?.vision && (
                <div className="vision-result">
                  <b>
                    {overview.photo.vision.common_name || overview.photo.vision.species_guess || (lang === 'ar' ? 'الصنف غير محدد' : 'Species uncertain')}
                    {overview.photo.vision.confidence != null ? ` · ${Math.round(overview.photo.vision.confidence * 100)}%` : ''}
                  </b>
                  <p>{overview.photo.vision.summary || (lang === 'ar' ? 'الملاحظات البصرية متوفرة.' : 'Visual observations are available.')}</p>
                  {Array.isArray(overview.photo.vision.visible_observations) && overview.photo.vision.visible_observations.length > 0 && (
                    <small>{t.observed_label}: {overview.photo.vision.visible_observations.join(' · ')}</small>
                  )}
                  {Array.isArray(overview.photo.vision.possible_stress_signs) && overview.photo.vision.possible_stress_signs.length > 0 && (
                    <small>{t.possible_stress_label}: {overview.photo.vision.possible_stress_signs.join(' · ')}</small>
                  )}
                  <small>{t.vision_disclaimer}</small>
                  {candidateSpecies && canControl && (
                    <button className="small-outline" style={{ marginTop: 8 }} onClick={useSuggestedSpecies} disabled={busy}>
                      {t.use_as_species}: {String(candidateSpecies)}
                    </button>
                  )}
                  <small>{t.species_candidate_note}</small>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Lower Grid: Decisions & AI Chat */}
        <section className="lower-grid">
          <div className="panel decisions-panel">
            <div className="panel-head">
              <div>
                <span className="section-overline">{t.decision_engine}</span>
                <h3>{t.recent_decisions}</h3>
              </div>
              <ShieldCheck size={19} className="muted-icon" />
            </div>

            {decisions.length ? (
              <div className="decision-list">
                {decisions.slice(0, 5).map((d: any) => (
                  <div className="decision-row" key={d.id}>
                    <span className={`decision-icon ${d.decision === 'water' ? 'water' : 'skip'}`}>
                      {d.decision === 'water' ? <Droplets size={15} /> : <ShieldCheck size={15} />}
                    </span>
                    <div className="decision-main">
                      <b>{String(d.decision).replace('_', ' ')}</b>
                      <p>{d.reason}</p>
                      <small>{new Date(d.created_at).toLocaleString(lang === 'ar' ? 'ar-EG' : [])}</small>
                    </div>
                    <span className="source-tag">{d.source}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-small">{t.no_decisions}</div>
            )}
          </div>

          <div className="panel assistant-panel">
            <div className="panel-head">
              <div>
                <span className="section-overline">{t.plant_knowledge}</span>
                <h3>{t.ask_plant}</h3>
              </div>
              <span className="ai-tag">{t.data_grounded}</span>
            </div>
            <p className="assistant-intro">{t.assistant_intro}</p>
            <form className="chat-form" onSubmit={sendChat}>
              <input
                value={chatText}
                onChange={e => setChatText(e.target.value)}
                placeholder={t.chat_placeholder}
              />
              <button disabled={busy || !chatText.trim()} aria-label={t.send_btn}>
                <Send size={16} />
              </button>
            </form>

            {chatAnswer && (
              <div className="chat-answer">
                <b>{t.assistant_name}</b>
                <p>{chatAnswer}</p>
              </div>
            )}

            <div className="suggestions">
              <button onClick={() => setChatText(t.prompt_root)}>{lang === 'ar' ? 'رطوبة الجذور حالياً' : 'Current root moisture'}</button>
              <button onClick={() => setChatText(t.prompt_analyze)}>{lang === 'ar' ? 'تحليل حالة النبات الشاملة' : 'Analyze current condition'}</button>
              <button onClick={() => setChatText(t.prompt_summary)}>{lang === 'ar' ? 'تلخيص الظروف الحالية' : 'Summarize conditions'}</button>
            </div>
          </div>
        </section>

        {/* Bottom Grid: Plant Profile & Diary */}
        <section className="lower-grid bottom-grid">
          <div className="panel profile-panel" id="plant-profile">
            <div className="panel-head">
              <div>
                <span className="section-overline">{t.knowledge_base}</span>
                <h3>{t.plant_profile}</h3>
              </div>
              <button className="small-outline" onClick={() => setShowAdd(!showAdd)}>
                <Plus size={14} /> {t.add_plant}
              </button>
            </div>

            {selected && (
              <div className="profile-details">
                <div className="profile-icon">
                  <Leaf size={21} />
                </div>
                <div className="profile-copy">
                  <b>{selected.species || t.species_unconfirmed}</b>
                  <span>{selected.name} · {selected.growth_stage || t.growth_stage_unset}</span>
                  <small>{t.ideal_range}: {selected.ideal_moisture_min}–{selected.ideal_moisture_max}%</small>
                  <small>
                    {t.source_label}:{' '}
                    {(selected as any).species_source === 'manual'
                      ? t.source_manual
                      : (selected as any).species_source === 'ai_suggested'
                      ? t.source_ai
                      : t.source_unconfirmed}
                  </small>
                </div>
                <span className="profile-id">{selected.plant_id}</span>
              </div>
            )}

            <div className="species-override">
              <label htmlFor="species-override-input">{t.species_override_label}</label>
              <div>
                <input
                  id="species-override-input"
                  value={speciesEdit}
                  onChange={e => setSpeciesEdit(e.target.value)}
                  placeholder={t.species_placeholder}
                />
                <button className="small-outline" onClick={saveSpecies} disabled={busy}>
                  {t.save_species}
                </button>
              </div>

              {speciesSuggestions.length > 0 && (
                <div className="species-suggestions" aria-label="Plant database matches">
                  {speciesSuggestions.map((item: any) => (
                    <button
                      key={item.slug}
                      type="button"
                      onClick={() => {
                        setSpeciesEdit(item.common_name);
                        setSpeciesSuggestions([]);
                      }}
                    >
                      <b>{item.common_name}</b>
                      <span>{item.slug.replace(/_/g, ' ')} · {item.source_name}</span>
                    </button>
                  ))}
                </div>
              )}
              <small>{t.species_db_hint}</small>
            </div>

            {showAdd && (
              <form className="add-form" onSubmit={addPlant}>
                <div className="form-grid">
                  <label>
                    {t.form_plant_id}
                    <input
                      required
                      pattern="[A-Za-z0-9_-]+"
                      value={newPlant.plant_id}
                      onChange={e => setNewPlant({ ...newPlant, plant_id: e.target.value })}
                      placeholder="plant02"
                    />
                  </label>
                  <label>
                    {t.form_name}
                    <input
                      required
                      value={newPlant.name}
                      onChange={e => setNewPlant({ ...newPlant, name: e.target.value })}
                      placeholder={lang === 'ar' ? 'نبات الطماطم' : 'Tomato plant'}
                    />
                  </label>
                  <label>
                    {t.form_species}
                    <input
                      value={newPlant.species}
                      onChange={e => setNewPlant({ ...newPlant, species: e.target.value })}
                      placeholder={lang === 'ar' ? 'طماطم' : 'Tomato'}
                    />
                  </label>
                  <label>
                    {t.form_stage}
                    <input
                      value={newPlant.growth_stage}
                      onChange={e => setNewPlant({ ...newPlant, growth_stage: e.target.value })}
                      placeholder={lang === 'ar' ? 'بادرة' : 'Seedling'}
                    />
                  </label>
                </div>
                <div className="form-grid">
                  <label>
                    {t.form_min_moist}
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={newPlant.ideal_moisture_min}
                      onChange={e => setNewPlant({ ...newPlant, ideal_moisture_min: Number(e.target.value) })}
                    />
                  </label>
                  <label>
                    {t.form_max_moist}
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={newPlant.ideal_moisture_max}
                      onChange={e => setNewPlant({ ...newPlant, ideal_moisture_max: Number(e.target.value) })}
                    />
                  </label>
                </div>
                <button className="primary-btn" disabled={busy}>
                  {t.form_save}
                </button>
              </form>
            )}
          </div>

          <div className="panel diary-panel" id="plant-diary">
            <div className="panel-head">
              <div>
                <span className="section-overline">{t.daily_notes}</span>
                <h3>{t.plant_diary}</h3>
              </div>
              <button className="small-outline" onClick={generateDiary} disabled={busy}>
                <Plus size={14} /> {t.generate_entry}
              </button>
            </div>
            {diary.length ? (
              <div className="diary-entry">
                <div className="diary-date">{diary[0].day}</div>
                <p>{diary[0].content}</p>
                <small>{t.diary_generated_from}</small>
              </div>
            ) : (
              <div className="empty-small">{t.no_diary_yet}</div>
            )}
          </div>
        </section>

        <footer>
          <div className="footer-brand">
            <Sprout size={16} /> {t.brand_name}
          </div>
          <span>{t.footer_prototype}</span>
          <span className="footer-note">
            <CircleAlert size={13} /> {t.footer_freshness_warning}
          </span>
        </footer>
      </main>

      {/* Mobile Download Modal */}
      {showDownloads && (
        <div className="download-backdrop" role="presentation" onClick={() => setShowDownloads(false)}>
          <section
            className="download-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="download-title"
            onClick={e => e.stopPropagation()}
          >
            <button className="download-close" onClick={() => setShowDownloads(false)} aria-label={t.close}>
              <X size={18} />
            </button>
            <div className="download-mark">
              <Sprout size={25} />
            </div>
            <span className="section-overline">{t.download_eyebrow}</span>
            <h2 id="download-title">{t.download_title}</h2>
            <p>{t.download_desc}</p>

            <div className="download-options">
              <div className="download-option android-option">
                <Smartphone size={24} />
                <div>
                  <b>{t.android_app}</b>
                  <small>{t.android_sub}</small>
                </div>
                {androidDownload ? (
                  <a className="download-choice" href={androidDownload} download="Greetopia.apk">
                    <Download size={14} /> APK
                  </a>
                ) : deferredInstall ? (
                  <button className="download-choice" onClick={installPwa}>
                    {t.install}
                  </button>
                ) : (
                  <span className="build-status">{t.build_required}</span>
                )}
              </div>

              <div className="download-option ios-option">
                <Apple size={24} />
                <div>
                  <b>{t.ios_app}</b>
                  <small>{t.ios_sub}</small>
                </div>
                {iosDownload ? (
                  <a className="download-choice" href={iosDownload}>
                    <Download size={14} /> IPA
                  </a>
                ) : (
                  <span className="build-status">{t.signing_required}</span>
                )}
              </div>
            </div>

            <div className="download-help">
              <b>{deferredInstall ? t.install_this_device : t.native_setup}</b>
              <p>{deferredInstall ? t.install_this_desc : t.native_setup_desc}</p>
              <small>{t.iphone_add_to_home}</small>
            </div>

            <a className="download-doc-link" href="https://capacitorjs.com/docs" target="_blank" rel="noreferrer">
              {t.native_docs_link} <ExternalLink size={13} />
            </a>
          </section>
        </div>
      )}

      {loading && (
        <div className="loading-indicator">
          <RefreshCw size={14} /> {t.syncing_data}
        </div>
      )}
    </div>
  );
}

export default App;
