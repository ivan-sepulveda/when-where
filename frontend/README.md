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
this automatically on every push — no `vercel.json` needed for a plain
static SPA like this one.
