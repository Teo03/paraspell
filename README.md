# ParaSpell

Parallel Spell Checker — a web-based spell-checking application with a parallelized backend that distributes work across CPU cores for fast, scalable processing of large texts.

Team 1 — Edon Fetaji, Edi Rizvani, Dea Jadrovska, Teodor Bogoeski, Blerona Muladauti.

## Repository structure

```
paraspell/
├── apps/
│   ├── backend/    FastAPI service — parallel spell-check engine
│   └── frontend/   React + Vite + shadcn/ui web client
├── docker-compose.yml
├── .env.example
└── .github/workflows/
```

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Frontend → http://localhost:5173
Backend  → http://localhost:8000

## Local development

### Backend

```bash
cd apps/backend
uv sync
uv run uvicorn app.main:app --reload
```

### Frontend

```bash
cd apps/frontend
pnpm install
pnpm dev
```

## Environment variables

See `.env.example`. Key settings:

| Variable              | Default | Description                                      |
|-----------------------|---------|--------------------------------------------------|
| `MAX_UPLOAD_SIZE_MB`  | `20`    | Max accepted file upload size                    |
| `MAX_SUGGESTIONS`     | `5`     | Correction candidates returned per misspelled word |
| `WORKER_COUNT`        | `auto`  | Parallel workers (`auto` → `os.cpu_count()`)     |
