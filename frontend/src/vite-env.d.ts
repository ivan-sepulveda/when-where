/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Optional -- frontend/.env.local.example is not committed as .env.local
  // by default, so this can genuinely be undefined (see the fallback in
  // src/pages/Destinations.tsx).
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
