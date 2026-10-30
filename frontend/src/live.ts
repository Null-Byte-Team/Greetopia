import { useEffect, useRef } from 'react';
import { wsUrl } from './api';

/** Live updates over WebSocket with exponential-backoff reconnect. The server never replays missed events, so every (re)connect
 *  calls onResync() and the caller re-fetches the full state. Polling in the caller remains the fallback while disconnected. */
export function useLive(enabled: boolean, onEvent: (msg: any) => void, onResync: () => void, onStatus: (connected: boolean) => void) {
  const handlers = useRef({ onEvent, onResync, onStatus });
  handlers.current = { onEvent, onResync, onStatus };

  useEffect(() => {
    if (!enabled || typeof WebSocket === 'undefined') return;
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;
    let delay = 1000;
    let stopped = false;

    const connect = () => {
      const token = localStorage.getItem('greetopia_token');
      if (!token || stopped) return;
      try {
        ws = new WebSocket(wsUrl());
      } catch {
        return;
      }
      ws.onopen = () => ws?.send(JSON.stringify({ type: 'auth', token }));
      ws.onmessage = ev => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'hello') {
            delay = 1000;
            handlers.current.onStatus(true);
            handlers.current.onResync();
            ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('ping'), 25000);
          } else if (msg.type === 'resync') {
            handlers.current.onResync();
          } else {
            handlers.current.onEvent(msg);
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = ev => {
        handlers.current.onStatus(false);
        if (ping) clearInterval(ping);
        if (stopped || ev.code === 4401) return; // 4401 = rejected token: the REST layer signs the user out
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 30000);
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      if (ping) clearInterval(ping);
      ws?.close();
    };
  }, [enabled]);
}
