# Phase 2 Kanban frontend overlay

This overlay was prepared for the existing React + TypeScript + Vite 8 scaffold. It intentionally **does not** replace `package.json`, `package-lock.json`, `tsconfig*.json`, or the scaffold's linter configuration.

## Installation from WSL

1. Back up the frontend source and Vite config before copying files.
2. Extract this archive to the existing `frontend/` directory (not to the repository root).
3. In `frontend/`, run:

```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
npm pkg set 'scripts.test=vitest run'
npm run lint
npm test
npm run build
```

## Running locally

Start PostgreSQL as configured for the existing backend, then run FastAPI from `backend/`:

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

In another terminal, from `frontend/`:

```bash
npm run dev
```

Visit http://localhost:5173. The Vite proxy forwards `/api` requests to http://127.0.0.1:8000. Check `curl -i http://127.0.0.1:8000/api/health` first.

## Implementation notes

- `src/types.ts`: Mirrors Pydantic TaskRead and TaskStatus.
- `src/api.ts`: Centralizes HTTP requests, JSON handling, and 204 No Content.
- `src/App.tsx`: React task state, CRUD operations, status transitions, loading/errors.
- `src/style.css`: Responsive three-column layout.
- `vite.config.ts`: Same-origin development proxy to FastAPI.
- `vitest.config.ts`: Isolated jsdom test configuration.
- `tests/App.test.tsx`: Mocked API tests for loading, creating, moving tasks.

Editing uses browser prompts; deletion uses a confirmation dialog. They are simple, functional starting points rather than a final UX design.
