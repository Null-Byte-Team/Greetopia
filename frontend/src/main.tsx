import { Capacitor } from '@capacitor/core';
import React from 'react'; import { createRoot } from 'react-dom/client'; import App from './App'; import './styles.css';
const platform = Capacitor.getPlatform();
document.documentElement.classList.add(`platform-${platform}`);
if (Capacitor.isNativePlatform()) document.documentElement.classList.add('native-app');
if (!Capacitor.isNativePlatform() && 'serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => undefined));
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
