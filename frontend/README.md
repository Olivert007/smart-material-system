# Smart Material System — Frontend (F1)

Vue 3 + Vite + Element Plus. All API calls use relative `API_BASE="/api/v1"` (no hardcoded backend/vLLM).

## Dev

```bash
# terminal 1 — API
cd /workspace/2026-07/smart-material-system
./scripts/start_api.sh

# terminal 2 — UI
cd frontend
npm install --legacy-peer-deps
npm run dev
# http://127.0.0.1:5173
```

Proxy: `/api` `/events` `/health` → `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8010`).

## OpenAPI types

```bash
npm run api:generate   # from ../deploy/openapi.json
npm run api:check      # fails if generated types drift
```
