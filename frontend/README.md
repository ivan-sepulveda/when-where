# when-where frontend

React + Vite + TypeScript. `/destinations` now talks to a real backend
(`../backend`, see its README) when the user searched with a date range:
`GET /api/destinations/top10` returns the top 10 countries for those
dates, weather included. Without a date range (e.g. clicking
"Destinations" in the nav directly), it falls back to fetching
`OVERARCHING_TRIP_SCORE_BY_COUNTRY.json` straight from this repo's `main`
branch on GitHub and ranking by the static `overarching_score` — no
weather in that path, just whatever's cheapest to show when there's no
date range to resolve against.

## Local dev

```
cd frontend
cp .env.local.example .env.local   # sets VITE_API_BASE_URL for the backend
npm install
npm run dev
```

`../backend` needs to be running separately (`uvicorn app.main:app --reload
--port 8000`, see `backend/README.md`) for the date-aware path to work.
Without it, searching with dates will show an error — the no-dates
fallback still works either way.

## Build

```
npm run build
```

Outputs static files to `dist/`. Vercel's zero-config Vite preset runs
this automatically on every push. Now that the app has real client-side
routes (react-router, e.g. `/destinations`), `vercel.json` adds a
catch-all rewrite to `index.html` — without it, a direct load or refresh
on `travel.iesepulveda.com/destinations` would 404 on Vercel's static
hosting, since only Vite's own dev server has SPA fallback built in.

`vite build` always runs in Vite's "production" mode (Vercel prod and
preview deploys alike), so it picks up `VITE_API_BASE_URL` from the
committed `.env.production` — `https://when-where.onrender.com` — with
no Vercel dashboard env var required. `.env.production` isn't a secret
(it's this project's own public API URL), which is why it's a
`.gitignore` exception rather than left to per-environment dashboard
config that's easy to leave unset on a new preview branch.
