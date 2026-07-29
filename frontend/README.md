# when-where frontend

Minimal React + Vite + TypeScript shell. No backend is wired up yet — this
exists to get a real deploy pipeline (GitHub → Vercel → `travel.iesepulveda.com`)
working before any real UI is built on top of it.

## Local dev

```
cd frontend
npm install
npm run dev
```

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
