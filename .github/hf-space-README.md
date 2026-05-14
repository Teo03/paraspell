---
title: ParaSpell Backend
emoji: 📝
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# ParaSpell Backend

Parallel spell-checker API for [ParaSpell](https://github.com/Teo03/paraspell) — a class project grounded in Petrushevski & Zdraveski, *Accelerating Spell Checking with Parallel Processing Techniques* (ICAI'25).

This Space hosts only the **backend** (FastAPI + ProcessPoolExecutor). The web UI lives at the GitHub repo's Vercel deployment.

> **Free-tier note**: the CPU Basic instance this Space runs on has 2 vCPUs. The parallel pipeline still works, but the 7× speedup figure from the paper requires ≥8 cores — upgrade the Space hardware in Settings if you need to reproduce that.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Service banner |
| `GET` | `/health` | Liveness probe |
| `POST` | `/check/text` | Spell-check JSON body `{"text": "..."}` |
| `POST` | `/check/file` | Spell-check uploaded `.txt` / `.docx` / `.pdf` |

Full OpenAPI docs at `/docs`.

## Configuration

Set these as **Variables** (or **Secrets**) in this Space's Settings:

| Variable | Default | Purpose |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed origins — set this to your Vercel deploy URL. |
| `MAX_UPLOAD_SIZE_MB` | `20` | Reject larger uploads with HTTP 400. |
| `MAX_SUGGESTIONS` | `5` | Top-N corrections returned per misspelled word. |
| `WORKER_COUNT` | `auto` | Parallel worker count; `auto` → `os.cpu_count()`. |

## Source

The contents of this Space are auto-deployed from the `apps/backend/` directory of the [GitHub repo](https://github.com/Teo03/paraspell) by the `deploy-hf.yml` workflow on every push to `main`. Don't edit files in this Space directly — they will be overwritten on the next deploy.
