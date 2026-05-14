# ParaSpell

Parallel Spell Checker — a web-based spell-checking application with a parallelized backend that distributes work across CPU cores for fast, scalable processing of large texts.

Implementation grounded in **Petrushevski & Zdraveski, "Accelerating Spell Checking with Parallel Processing Techniques", ICAI'25**, which demonstrates ~7× speedup over sequential spell checking on an 8-core machine.

## Team 1

| Member            | Student ID |
| ----------------- | ---------- |
| Edon Fetaji       | 221517     |
| Edi Rizvani       | 221587     |
| Dea Jadrovska     | 221526     |
| Teodor Bogoeski   | 221511     |
| Blerona Muladauti | 221541     |
| Ivana Kamchevska  | 259081     |

## Architecture

The frontend is a React SPA; the backend is a FastAPI service that preprocesses input text, splits it into balanced chunks, and dispatches them to a `ProcessPoolExecutor` of worker processes. Each worker loads the full 370k-word dictionary and Soundex map into memory once at startup, then performs phonetic filtering (Soundex) followed by edit-distance ranking (Levenshtein) on its chunk. Results are merged in the main process and returned over a single HTTP response. No user content is persisted — the request is the entire lifecycle (NFR-10).

## Repository structure

```
paraspell/
├── apps/
│   ├── backend/    FastAPI service — parallel spell-check engine
│   └── frontend/   React + Vite + Tailwind + shadcn/ui web client
├── docker-compose.yml
├── .env.example
├── .github/workflows/
└── paraspell.code-workspace   # VS Code multi-root workspace
```

## Prerequisites

Pick **one** of the two paths below.

### Path A — Docker (recommended)

| Tool           | Minimum | Notes                                        |
| -------------- | ------- | -------------------------------------------- |
| Docker Engine  | 24+     | Docker Desktop on macOS / Windows works fine |
| Docker Compose | v2      | bundled with modern Docker Desktop           |

Nothing else needs to be installed locally.

### Path B — Run services natively

| Tool    | Minimum    | Notes                                      |
| ------- | ---------- | ------------------------------------------ |
| Python  | 3.10+      | 3.12 used in the backend Dockerfile        |
| Node.js | 20.x LTS   | matches the frontend Dockerfile base image |
| pnpm    | 8.15+      | install via `corepack enable`              |
| Git     | any recent | required by `pnpm install` for some deps   |

### Hardware (deployment, per SRS §6.3)

- CPU: 4 cores minimum, 8+ recommended for peak parallel speedup
- RAM: 4 GB minimum (each spell-check worker loads the full dictionary into memory)
- OS: Linux (Ubuntu 22.04 LTS recommended for production)

## Quick start (Docker)

```bash
git clone https://github.com/Teo03/paraspell.git
cd paraspell
cp .env.example .env
docker compose up --build
```

| Service        | URL                          | Notes                           |
| -------------- | ---------------------------- | ------------------------------- |
| Frontend       | http://localhost:5173        | Vite dev server with HMR        |
| Backend        | http://localhost:8000        | FastAPI, auto-reloading uvicorn |
| Backend health | http://localhost:8000/health | returns `{"status":"ok"}`       |

Tear down with `docker compose down` (add `-v` to also drop the named `node_modules` volumes).

## Local development (without Docker)

### Backend

The current backend is a placeholder hello-world while the FastAPI structure (NFR-12) is being built. It uses `pip` and `requirements.txt` for now; this will move to a proper `pyproject.toml` (uv) once the real structure lands.

```bash
cd apps/backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run all backend tests (from the repo root, with the venv activated):

```bash
pytest apps/backend --ignore=apps/backend/app
```

This is the same command CI runs — see [Running tests](#running-tests) for verbose output, single-file runs, and other invocations.

### Frontend

```bash
cd apps/frontend
pnpm install
pnpm dev
```

The dev server is configured to bind on `0.0.0.0:5173` (so it works identically inside the Docker container).

## Environment variables

All variables live in a single root `.env` file. See `.env.example` for paper-grounded defaults and per-variable rationale.

| Variable             | Default                 | Description                                                                                      | Source                    |
| -------------------- | ----------------------- | ------------------------------------------------------------------------------------------------ | ------------------------- |
| `MAX_UPLOAD_SIZE_MB` | `20`                    | Hard cap on file uploads; larger requests are rejected with HTTP 400                             | SRS NFR-02, NFR-08, UC-02 |
| `MAX_SUGGESTIONS`    | `5`                     | Number of correction candidates returned per misspelled word                                     | SRS UC-03, §5.2.4         |
| `WORKER_COUNT`       | `auto`                  | Parallel worker processes; `auto` resolves to `os.cpu_count()` (peak speedup per paper Table II) | SRS FR-06, FR-07          |
| `CHUNK_SIZE`         | `auto`                  | Words per chunk handed to each worker; `auto` = `ceil(total_words / WORKER_COUNT)`               | SRS NFR-13                |
| `CORS_ORIGINS`       | `http://localhost:5173` | Comma-separated origins permitted by FastAPI CORS middleware                                     | SRS NFR-11                |
| `VITE_API_BASE_URL`  | `http://localhost:8000` | Base URL the React app uses for API calls                                                        | —                         |

The same values are also stored as **GitHub repository variables** (`gh variable list --repo Teo03/paraspell`) for use in the CI pipeline.

## API endpoints

The current backend is a placeholder; real endpoints will land with Part 4.

| Method | Path      | Description                                             |
| ------ | --------- | ------------------------------------------------------- |
| `GET`  | `/`       | Service banner                                          |
| `GET`  | `/health` | Liveness probe (used by the docker-compose healthcheck) |

Planned endpoints (Part 4 / Trello):

| Method | Path          | Description                                 | Card  |
| ------ | ------------- | ------------------------------------------- | ----- |
| `POST` | `/check/text` | Spell-check pasted text                     | FR-05 |
| `POST` | `/check/file` | Spell-check an uploaded .txt / .docx / .pdf | FR-02 |

## Common scripts

```bash
# from the repo root
pnpm dev:frontend          # Vite dev server (proxies to backend)
pnpm build:frontend        # Production frontend build
pnpm lint:frontend         # ESLint on the frontend

# inside apps/backend
uvicorn app.main:app --reload     # backend dev server
```

## Running tests

The backend test suite lives under `apps/backend/tests/` and is driven by [pytest](https://docs.pytest.org/). The same command CI uses is the one to run locally — no extra setup, no `cd` into the package, no `PYTHONPATH` shuffle (the test suite's `conftest.py` handles that).

### Prerequisites

The tests use the committed `apps/backend/app/data/words.marisa` and `apps/backend/app/data/soundex.sqlite` artifacts. If you have a fresh checkout and either file is missing, regenerate them first:

```bash
python apps/backend/scripts/build_dict.py            # produces words.marisa
python apps/backend/scripts/build_soundex_sqlite.py  # produces soundex.sqlite
```

You only need to run these if the data files are missing — they're committed and shipped with the repo.

### Run the whole backend suite

From the repo root:

```bash
pytest apps/backend --ignore=apps/backend/app
```

This is the exact command the CI workflow runs (`.github/workflows/ci.yml`), so green here means green in CI. Expect ~66 tests covering Soundex, Dictionary, and the worker pipeline.

### Useful invocations

```bash
# Verbose — print every test name as it runs
pytest apps/backend --ignore=apps/backend/app -v

# Run only one file
pytest apps/backend/tests/test_soundex.py

# Run only one class or one test
pytest apps/backend/tests/test_dictionary.py::TestLRUCache
pytest apps/backend/tests/test_worker.py::TestRanking::test_suggestions_sorted_descending

# Filter by name substring (e.g. every parametrised typo case)
pytest apps/backend -k "typo"

# Stop at the first failure
pytest apps/backend -x
```

### Running tests inside Docker

If you'd rather not install Python deps locally, run pytest inside the running backend container:

```bash
docker compose exec backend pytest /app/tests --ignore=/app/app
```

(Note: this requires the test folder and data files to be copied into the image. If they aren't yet — the production `Dockerfile` only copies `app/` — run pytest from the host instead.)

## Team notes

- dwyl's wordlist contains some archaic / typo spellings as "valid" (e.g. `untill`, `embarras`, `accomodate`, `wierd`, `calender`, `cemetary`, `noticable`, `priviledge`). `scripts/dict_blocklist.txt` lists the offenders and `build_dict.py` drops them before serialising the trie. Add more entries to the blocklist (one word per line, `#` for comments) and rerun the two build scripts to extend coverage.
- Suggestion ranking uses a frequency-blended score: pure Levenshtein gives the base, then `log10(count+1) / 9` (clamped to 1) pulls common candidates toward the top. Frequencies come from Norvig's `count_1w.txt` (~333k web 1-gram counts), cached by `scripts/build_freq.py` and baked into `soundex.sqlite`. Words missing from Norvig's data get freq=0 → no boost → behaviour reduces to pure Levenshtein.
- Linux copy-on-write only shares pages with `mp.get_context("fork")`. Edi's Part 3 should use `fork` (the Linux default); `spawn` would re-execute imports and rebuild the Soundex index per worker. Flag this in the Part 3 PR.

## Project ownership

Work is split across six tracks (`SRS Part 1 → Part 6`):

| Part | Scope                                                                        | Owner        |
| ---- | ---------------------------------------------------------------------------- | ------------ |
| 1    | Project Setup & DevOps (monorepo, Docker, env, CI, README)                   | Teodor       |
| 2    | Dictionary & Algorithms (370k dictionary, MARISA-trie, Soundex, Levenshtein) | Edon         |
| 3    | Parallel Spell-Check Engine (chunking, ProcessPoolExecutor, fault tolerance) | Edi          |
| 4    | Backend API Layer (FastAPI, endpoints, file extraction, CORS)                | Dea          |
| 5    | Frontend: Input, Layout & Stats                                              | Blerona      |
| 6    | Frontend: Results Pane & Corrections                                         | _unassigned_ |

## Reference

Petrushevski, N. & Zdraveski, V. (2025). _Accelerating Spell Checking with Parallel Processing Techniques._ International Conference on Automatics and Informatics (ICAI'25), Varna, Bulgaria.
