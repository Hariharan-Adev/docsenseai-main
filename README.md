# Simple RAG

A tenant-aware RAG application with durable asynchronous ingestion, document
versioning, structured citations, Qdrant retrieval, a FastAPI API, and React.

## Project structure

- `frontend/` - React/Vite app that talks to the backend API.
- `backend/` - FastAPI backend workspace with source, scripts, tests, and worker commands.
- `backend/src/app/` - importable FastAPI application package, including routes, services, prompts, and utilities.
- `backend/scripts/` - backend maintenance and vector-store scripts.
- `backend/tests/` - backend test suites.
- `db/` - SQLite setup, schemas, data models, migrations, seeds, local database files, uploads, and local vector storage.
- `docs/` - architecture notes, runbooks, security reports, and archived change-set material.
- `tools/` - one-off maintenance/helper utilities that are not part of the running app.
- `artifacts/` - generated support artifacts, such as spreadsheet request JSON files.

## Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Run the durable worker in a separate terminal/process:

```powershell
cd backend
.\.venv312\Scripts\python.exe -m app.worker
```

The backend runs on `http://127.0.0.1:8000` by default. Put secrets such as `GROQ_API_KEY`, `JWT_SECRET_KEY`, and rate-limit values in `backend/.env`. Runtime SQLite files and uploads are stored under `db/data/`.

The API process only validates and enqueues uploads. The worker owns extraction,
chunking, embedding, and Qdrant upserts. Jobs use durable SQLite state,
idempotency keys, compare-and-set claims, stale-lock recovery, exponential
backoff with jitter, terminal error codes, retry, cancellation, and polling.

For Docker-backed Qdrant, start it from the repository root:

```powershell
docker compose up -d qdrant
```

For local file-backed Qdrant, use `QDRANT_MODE=local` and `QDRANT_LOCAL_PATH=db/qdrant_data` in `backend/.env`.

After the first metadata migration, backfill existing current-version vectors:

```powershell
cd backend
.\.venv312\Scripts\python.exe -m app.reindex
```

`GET /health/ready` checks SQLite and Qdrant. `GET /metrics` exposes ingestion
and active-document gauges. In production set `APP_ENVIRONMENT=production` and
use a persistent Qdrant service through `QDRANT_URL`; in-memory Qdrant is only a
development/test fallback. Before migration, the application writes
`rag_new.db.pre_multitenant_rag.bak` once. To roll back, stop API and worker
processes, restore that file as `rag_new.db`, and deploy the prior application
version. New queued/version records created after the migration are not present
in the backup.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend uses `VITE_API_BASE_URL` when set, and otherwise calls `http://127.0.0.1:8000`.

## Notes

Local runtime files are ignored by Git, including `.env`, virtual environments,
`node_modules`, SQLite databases, uploaded documents, build output, local vector
storage, and Python caches.
