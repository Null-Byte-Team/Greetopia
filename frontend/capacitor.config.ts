import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.greetopia.plantcare',
  appName: 'Greetopia',
  webDir: 'dist',
  bundledWebRuntime: false,
  ios: { contentInset: 'automatic', backgroundColor: '#f4f7f0' },
  android: { backgroundColor: '#f4f7f0' }
};

export default config;
