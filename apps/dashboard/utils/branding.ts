// Branding read from env at request time (server-side), so a re-skin is a
// restart, not a rebuild. Defaults match the bundled "Voice agent" look.

export interface Branding {
  appName: string;
  brandColor: string;
  brandColorDark: string;
  faviconPath: string;
}

const DEFAULTS: Branding = {
  appName: 'Voice agent',
  brandColor: '#1b6df1',
  brandColorDark: '#1a6ad0',
  faviconPath: '/ico.png',
};

function normalizeColor(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  if (!trimmed) return fallback;
  return trimmed.startsWith('#') ? trimmed : `#${trimmed}`;
}

export function getBranding(): Branding {
  return {
    appName: process.env.APP_NAME?.trim() || DEFAULTS.appName,
    brandColor: normalizeColor(process.env.BRAND_COLOR, DEFAULTS.brandColor),
    brandColorDark: normalizeColor(process.env.BRAND_COLOR_DARK, DEFAULTS.brandColorDark),
    faviconPath: process.env.FAVICON_PATH?.trim() || DEFAULTS.faviconPath,
  };
}
