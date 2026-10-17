import { useState, useCallback, useEffect, useRef } from 'react';
import { Sprout, Mail, Lock, User, AlertCircle, Loader2, ArrowRight, Sun, Moon, Languages } from 'lucide-react';
import { Translations, Theme, Language } from './i18n';

const GOOGLE_CLIENT_ID =
  (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID ||
  '355615741600-5tfd5st7gr7ihnl81k78794u853u32qc.apps.googleusercontent.com';

/** Resolve the backend /api/v1 base URL the same way api.ts does. */
function getApiBase(): string {
  const envBase = (import.meta as any).env?.VITE_API_BASE;
  if (envBase) return envBase.replace(/\/+$/, '');
  if (typeof window !== 'undefined') {
    const { protocol, hostname, port } = window.location;
    if (protocol === 'http:' && (hostname === 'localhost' || hostname === '127.0.0.1') && port === '5173') {
      return `http://${hostname}:5000/api/v1`;
    }
  }
  return '/api/v1';
}

interface Props {
  t: Translations;
  theme: Theme;
  lang: Language;
  onAuth: (token: string, user: any) => void;
  toggleTheme?: () => void;
  toggleLang?: () => void;
  onContinueAsGuest?: () => void;
}

type Mode = 'signin' | 'signup';

export default function SignInPage({
  t,
  theme,
  lang,
  onAuth,
  toggleTheme,
  toggleLang,
  onContinueAsGuest,
}: Props) {
  const [mode, setMode] = useState<Mode>('signin');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const googleBtnRef = useRef<HTMLDivElement>(null);

  // ── Google One Tap / Button ────────────────────────────────────────────────
  const handleGoogleCredential = useCallback(
    async (response: any) => {
      setError('');
      setLoading(true);
      try {
        const res = await fetch(`${getApiBase()}/auth/google`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id_token: response.credential }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || t.auth_error_generic);
        onAuth(data.token, data.user);
      } catch (e: any) {
        setError(e.message || t.auth_error_generic);
      } finally {
        setLoading(false);
      }
    },
    [t, onAuth],
  );

  useEffect(() => {
    // Inject Google Identity Services script once
    const scriptId = 'google-gsi';
    if (!document.getElementById(scriptId)) {
      const s = document.createElement('script');
      s.id = scriptId;
      s.src = 'https://accounts.google.com/gsi/client';
      s.async = true;
      s.defer = true;
      document.head.appendChild(s);
    }

    // Poll until window.google is ready, then initialise
    let attempts = 0;
    const interval = setInterval(() => {
      if ((window as any).google?.accounts?.id) {
        clearInterval(interval);
        (window as any).google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleGoogleCredential,
          auto_select: false,
          ux_mode: 'popup',
        });
        if (googleBtnRef.current) {
          (window as any).google.accounts.id.renderButton(googleBtnRef.current, {
            theme: theme === 'dark' ? 'filled_black' : 'outline',
            size: 'large',
            width: googleBtnRef.current.offsetWidth || 320,
            locale: lang === 'ar' ? 'ar' : 'en',
            text: 'continue_with',
            shape: 'rectangular',
          });
        }
      }
      if (++attempts > 40) clearInterval(interval); // give up after 4 s
    }, 100);

    return () => clearInterval(interval);
  }, [theme, lang, handleGoogleCredential]);

  // Re-render Google button when theme/lang changes
  useEffect(() => {
    if ((window as any).google?.accounts?.id && googleBtnRef.current) {
      (window as any).google.accounts.id.renderButton(googleBtnRef.current, {
        theme: theme === 'dark' ? 'filled_black' : 'outline',
        size: 'large',
        width: googleBtnRef.current.offsetWidth || 320,
        locale: lang === 'ar' ? 'ar' : 'en',
        text: 'continue_with',
        shape: 'rectangular',
      });
    }
  }, [theme, lang]);

  // ── Email / Password Submit ────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const endpoint = mode === 'signup' ? '/auth/signup' : '/auth/signin';
      const body: any = { email, password };
      if (mode === 'signup') body.name = name;

      const res = await fetch(`${getApiBase()}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || t.auth_error_generic);
      onAuth(data.token, data.user);
    } catch (e: any) {
      setError(e.message || t.auth_error_generic);
    } finally {
      setLoading(false);
    }
  };

  const isRtl = lang === 'ar';

  return (
    <div className="auth-shell" data-theme={theme} dir={isRtl ? 'rtl' : 'ltr'}>
      <div className="auth-card">
        {/* Brand & Theme/Lang Controls */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div className="auth-brand" style={{ marginBottom: 0 }}>
            <div className="auth-brand-mark">
              <Sprout size={24} />
            </div>
            <div>
              <strong>{t.brand_name}</strong>
              <span>{t.brand_sub}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {toggleTheme && (
              <button className="icon-button" type="button" onClick={toggleTheme} title="Toggle theme">
                {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              </button>
            )}
            {toggleLang && (
              <button className="icon-button" type="button" onClick={toggleLang} title="Toggle language">
                <Languages size={15} />
              </button>
            )}
          </div>
        </div>

        {/* Heading */}
        <div className="auth-heading">
          <h1>{mode === 'signin' ? t.signin_heading : t.signup_heading}</h1>
          <p>{mode === 'signin' ? t.signin_sub : t.signup_sub}</p>
        </div>

        {/* Error */}
        {error && (
          <div className="auth-error">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {/* Email/Password Form */}
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {mode === 'signup' && (
            <div className="auth-field">
              <label htmlFor="auth-name">{t.name_label}</label>
              <div className="auth-input-wrap">
                <User size={16} className="auth-field-icon" />
                <input
                  id="auth-name"
                  type="text"
                  autoComplete="name"
                  required
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder={lang === 'ar' ? 'محمد أحمد' : 'John Doe'}
                />
              </div>
            </div>
          )}

          <div className="auth-field">
            <label htmlFor="auth-email">{t.email_label}</label>
            <div className="auth-input-wrap">
              <Mail size={16} className="auth-field-icon" />
              <input
                id="auth-email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password">{t.password_label}</label>
            <div className="auth-input-wrap">
              <Lock size={16} className="auth-field-icon" />
              <input
                id="auth-password"
                type="password"
                autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                required
                minLength={8}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>
          </div>

          <button className="auth-submit-btn" type="submit" disabled={loading}>
            {loading ? (
              <>
                <Loader2 size={16} className="auth-spin" /> {t.signing_in}
              </>
            ) : (
              <>
                {mode === 'signin' ? t.btn_signin : t.btn_signup} <ArrowRight size={15} />
              </>
            )}
          </button>
        </form>

        {/* Divider */}
        <div className="auth-divider">
          <span />
          <small>{lang === 'ar' ? 'أو' : 'or'}</small>
          <span />
        </div>

        {/* Google Button — rendered by Google Identity Services SDK */}
        <div className="auth-google-wrap" ref={googleBtnRef} />

        {/* Mode Switch */}
        <button
          className="auth-switch-btn"
          type="button"
          onClick={() => {
            setMode(m => (m === 'signin' ? 'signup' : 'signin'));
            setError('');
          }}
        >
          {mode === 'signin' ? t.switch_to_signup : t.switch_to_signin}
        </button>

        {/* Continue as guest */}
        {onContinueAsGuest && (
          <button
            className="auth-switch-btn"
            type="button"
            style={{ marginTop: 6, fontSize: 11, opacity: 0.8 }}
            onClick={onContinueAsGuest}
          >
            {lang === 'ar' ? '← المتابعة كزائر (معاينة اللوحة)' : 'Continue as Guest (Preview) →'}
          </button>
        )}
      </div>

      {/* Background decorative blobs */}
      <div className="auth-blob auth-blob-a" />
      <div className="auth-blob auth-blob-b" />
    </div>
  );
}
