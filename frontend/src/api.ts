import { Capacitor } from '@capacitor/core';
const API = import.meta.env.VITE_API_BASE || `http://${window.location.hostname}:5000/api/v1`;
export const API_ORIGIN = API.replace(/\/api\/v1\/?$/, '');
async function request<T>(path:string, init?:RequestInit):Promise<T>{const r=await fetch(`${API}${path}`,{...init,headers:{'Content-Type':'application/json','X-Greetopia-Platform':Capacitor.isNativePlatform()?Capacitor.getPlatform():'web',...(init?.headers||{})}});if(!r.ok){const body=await r.json().catch(()=>({detail:r.statusText}));throw new Error(body.detail||'Request failed');}return r.json();}
export const api={
 health:()=>request<any>('/health'),
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
