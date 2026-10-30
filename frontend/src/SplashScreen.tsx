import React from 'react';
import { Sprout, Sparkles } from 'lucide-react';
import { Translations, Theme, Language } from './i18n';

interface SplashScreenProps {
  t: Translations;
  theme: Theme;
  lang: Language;
  fading?: boolean;
  status?: string;
}

export default function SplashScreen({
  t,
  theme,
  lang,
  fading = false,
  status,
}: SplashScreenProps) {
  const isRtl = lang === 'ar';

  return (
    <div
      className={`splash-screen ${fading ? 'splash-fading' : ''}`}
      data-theme={theme}
      dir={isRtl ? 'rtl' : 'ltr'}
      aria-label="Loading Greetopia"
      role="status"
    >
      <div className="splash-ambient splash-ambient-1" />
      <div className="splash-ambient splash-ambient-2" />

      <div className="splash-content">
        {/* Animated Brand Badge */}
        <div className="splash-badge-wrap">
          <div className="splash-badge-halo" />
          <div className="splash-badge">
            <Sprout size={48} className="splash-icon" strokeWidth={2.2} />
          </div>
          <span className="splash-badge-sparkle">
            <Sparkles size={18} />
          </span>
        </div>

        {/* Brand Titles */}
        <h1 className="splash-title">{t.brand_name || 'Greetopia'}</h1>
        <p className="splash-sub">{t.brand_sub || 'Smart Plant Care & Monitoring'}</p>

        {/* Progress Bar & Status Text */}
        <div className="splash-progress-track">
          <div className="splash-progress-bar" />
        </div>
        <p className="splash-status">
          {status || (isRtl ? 'جاري الاتصال بنظام رعاية النباتات...' : 'Connecting to smart plant system...')}
        </p>
      </div>
    </div>
  );
}
