// Base URL of the backend API (see ../../backend/README.md).
// VITE_API_BASE_URL is set per-environment: frontend/.env.local for local
// dev, the committed frontend/.env.production (see that file's own
// comment for why it's committed) for production/preview builds. Falls
// back to the local dev default so this doesn't silently break if the
// env var isn't set for some reason.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
