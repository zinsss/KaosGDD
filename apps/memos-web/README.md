# KaosGDD Memos Web

One configurable frontend for the existing Memos backend.

## Boundary

- Memos `0.29.1` remains the canonical memo and attachment store.
- The browser calls the documented Memos v1 REST gateway through its own host.
- The Memos refresh token is an HttpOnly, host-only cookie.
- The short-lived access token remains in memory and is never persisted.
- Personal and Family run the same image with different runtime configuration.

## Phase 1

- password sign-in and refresh-token session restore
- creator-scoped memo list
- create, edit, delete, pin, and visibility
- Markdown rendering
- server-side content search and tag filtering

The dual-mode Tiptap editor and KaosPrint integration are later phases.

## Build and test

```bash
docker run --rm -v "$PWD:/app" -w /app node:24-alpine npm install
docker run --rm -v "$PWD:/app" -w /app node:24-alpine npm test
docker build -t kaosgdd-memos-web:0.1.0 .
```

## Runtime configuration

See `compose.production.yaml`. The image writes `config.js` at container start
from `APP_NAME`, `APP_MODE`, `MEMOS_BASE_URL`, `KAOSPRINT_URL`,
`DEFAULT_EDITOR_MODE`, `ALLOW_MARKDOWN_MODE`, and `THEME`.
