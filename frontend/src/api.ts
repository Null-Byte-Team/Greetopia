import { Capacitor } from '@capacitor/core';

// The API base must be explicit for deployed builds: set VITE_API_BASE=https://<your-backend>/api/v1.
// Local development uses the Vite proxy (/api -> http://127.0.0.1:5000). There is no hard-coded production fallback.
function resolveApiBase(): string {
  const envBase = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
  if (envBase) {
    if (
      typeof window !== 'undefined' &&
      window.location.protocol === 'https:' &&
      envBase.startsWith('http://') &&
      !envBase.includes('localhost') &&
      !envBase.includes('127.0.0.1')
    ) {
      return envBase.replace(/^http:\/\//i, 'https://').replace(/\/+$/, '');
    }
    return envBase.replace(/\/+$/, '');
  }
  if (Capacitor.isNativePlatform()) {
    throw new Error('VITE_API_BASE is not set. Native builds must be built with the HTTPS URL of your backend.');
  }
  return '/api/v1';
}

let API = '/api/v1';
let configError: string | null = null;
try {
  API = resolveApiBase();
} catch (e: any) {
  configError = e.message;
}

export const API_ORIGIN = API.startsWith('http') ? API.replace(/\/api\/v1\/?$/, '') : '';
export const apiConfigError = configError;
export const UNAUTHORIZED_EVENT = 'greetopia-unauthorized';

function errorMessage(body: any, fallback: string): string {
  const d = body?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && typeof d.message === 'string') return d.message;
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (configError) throw new Error(configError);
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('greetopia_token') : null;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Greetopia-Platform': Capacitor.isNativePlatform() ? Capacitor.getPlatform() : 'web',
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (init?.headers) Object.assign(headers, init.headers);
  const r = await fetch(`${API}${path}`, { ...init, headers });
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }));
    if (r.status === 401 && token && !path.startsWith('/auth/signin') && !path.startsWith('/auth/signup') && !path.startsWith('/auth/google')) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new Error(errorMessage(body, 'Request failed'));
  }
  return r.json();
}

export const api = {
  health: () => request<any>('/health'),
  authMe: () => request<any>('/auth/me'),
  plants: () => request<any[]>('/plants'),
  plantKnowledge: (q: string) => request<any>(`/plant-knowledge?q=${encodeURIComponent(q)}&limit=8`),
  overview: (id: string) => request<any>(`/plants/${id}/overview`),
  history: (id: string) => request<any[]>(`/plants/${id}/readings/history?limit=80`),
  mode: (id: string, mode: 'auto' | 'manual') => request<any>(`/plants/${id}/mode`, { method: 'PATCH', body: JSON.stringify({ mode }) }),
  water: (id: string, seconds: number) => request<any>(`/plants/${id}/water`, { method: 'POST', body: JSON.stringify({ duration_seconds: seconds }) }),
  decision: (id: string) => request<any>(`/plants/${id}/decision`, { method: 'POST' }),
  decisions: (id: string) => request<any[]>(`/plants/${id}/decisions?limit=8`),
  events: (id: string) => request<any[]>(`/plants/${id}/events?limit=10`),
  chat: (id: string, question: string) => request<any>(`/plants/${id}/chat`, { method: 'POST', body: JSON.stringify({ question }) }),
  createPlant: (plant: any) => request<any>('/plants', { method: 'POST', body: JSON.stringify(plant) }),
  updatePlant: (id: string, patch: any) => request<any>(`/plants/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  analyzePhoto: (id: string) => request<any>(`/plants/${id}/photos/analyze`, { method: 'POST' }),
  diary: (id: string) => request<any[]>(`/plants/${id}/diary`),
  generateDiary: (id: string) => request<any>(`/plants/${id}/diary/generate`, { method: 'POST' }),
};
