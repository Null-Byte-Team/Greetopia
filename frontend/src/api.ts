import { Capacitor } from '@capacitor/core';

// Check for runtime service binding injected by Vercel (if running in serverless/Node functions).
const boundBackendUrl =
  typeof process !== 'undefined' && process.env?.BACKEND_URL
    ? `${process.env.BACKEND_URL.replace(/\/+$/, '')}/api/v1`
    : '';

// Reconcile with public paths and deployment environments:
// - Explicit env override: VITE_API_BASE
// - Service binding if available: boundBackendUrl
// - Mobile Capacitor native platform default: http://localhost:5000/api/v1
// - Standalone Vite dev server default (port 5173): http://${window.location.hostname}:5000/api/v1
// - Vercel multi-service routing default: /api/v1 (routes to backend service via Vercel rewrites)
function resolveApiBase(): string {
  const envBase = import.meta.env.VITE_API_BASE;
  if (envBase) {
    // If the page is on HTTPS, upgrade remote http:// URLs to https:// to prevent Mixed Content blocking
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
  if (boundBackendUrl) {
    return boundBackendUrl;
  }
  if (Capacitor.isNativePlatform()) {
    return 'http://localhost:5000/api/v1';
  }
  // Standalone local Vite dev server on HTTP
  if (
    typeof window !== 'undefined' &&
    window.location.protocol === 'http:' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
    window.location.port === '5173'
  ) {
    return `http://${window.location.hostname}:5000/api/v1`;
  }
  // On Vercel (or any HTTPS deployment), always use relative /api/v1.
  // This uses same-origin HTTPS and routes to the backend service via Vercel rewrites.
  return '/api/v1';
}

const API = resolveApiBase();
export const API_ORIGIN = API.startsWith('http') ? API.replace(/\/api\/v1\/?$/, '') : '';
async function request<T>(path:string, init?:RequestInit):Promise<T>{
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('greetopia_token') : null;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Greetopia-Platform': Capacitor.isNativePlatform() ? Capacitor.getPlatform() : 'web',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (init?.headers) {
    Object.assign(headers, init.headers);
  }
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers,
  });
  if(!r.ok){
    const body=await r.json().catch(()=>({detail:r.statusText}));
    throw new Error(body.detail||'Request failed');
  }
  return r.json();
}
export const api={
 health:()=>request<any>('/health'),
 authMe:()=>request<any>('/auth/me'),
 plants:()=>request<any[]>('/plants'),
 plantKnowledge:(q:string)=>request<any>(`/plant-knowledge?q=${encodeURIComponent(q)}&limit=8`),
 overview:(id:string)=>request<any>(`/plants/${id}/overview`),
 history:(id:string)=>request<any[]>(`/plants/${id}/readings/history?limit=80`),
 mode:(id:string,mode:'auto'|'manual')=>request<any>(`/plants/${id}/mode`,{method:'PATCH',body:JSON.stringify({mode})}),
 water:(id:string,seconds:number)=>request<any>(`/plants/${id}/water`,{method:'POST',body:JSON.stringify({duration_seconds:seconds})}),
 decision:(id:string)=>request<any>(`/plants/${id}/decision`,{method:'POST'}),
 decisions:(id:string)=>request<any[]>(`/plants/${id}/decisions?limit=8`),
 chat:(id:string,question:string)=>request<any>(`/plants/${id}/chat`,{method:'POST',body:JSON.stringify({question})}),
 createPlant:(plant:any)=>request<any>('/plants',{method:'POST',body:JSON.stringify(plant)}),
 updatePlant:(id:string,patch:any)=>request<any>(`/plants/${id}`,{method:'PATCH',body:JSON.stringify(patch)}),
 analyzePhoto:(id:string)=>request<any>(`/plants/${id}/photos/analyze`,{method:'POST'}),
 diary:(id:string)=>request<any[]>(`/plants/${id}/diary`),
 generateDiary:(id:string)=>request<any>(`/plants/${id}/diary/generate`,{method:'POST'}),
};
