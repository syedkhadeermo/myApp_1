# scRNA-seq Ligand Explorer

A single-operator FastAPI, React/Tailwind, MongoDB and Scanpy research demo. Upload a small H5AD dataset, enter a ligand SMILES and organ, and inspect the baseline expression variability of genes in that organ alongside molecular descriptors and saved analysis history. The repository includes an optional PyTorch Geometric GNN architecture, but does **not** include trained weights, binding targets, perturbation data or a validated disease model.

**Scientific boundary:** the app computes descriptive baseline gene variability from the uploaded data. It does not simulate ligand-induced expression changes or predict a cure. Protein names are gene-symbol proxies, the disease list is general organ context, and there are no inferred cures. Binding score is `null` because binding requires a specified protein target and validated assay/model. An operator may provide a separately trained, validated organ-specific GNN checkpoint for an experimental ligand–organ score; the UI labels it separately. This app is not for clinical decisions.

## Architecture

Browser → nginx (`/api/` proxy, static React) → FastAPI (API key, bounded upload, RDKit + Scanpy, optional GNN) → MongoDB (metadata, durable job queue, history). A single worker in the backend service claims jobs atomically and records results; queued/running jobs are recovered after a restart. H5AD bytes reside only in a private upload volume under a random UUID filename. Mongo holds metadata, SHA-256 and expiry. Rejected uploads are deleted immediately. Expired files are swept at startup, on new uploads, and every 10 minutes; Mongo TTL indexes expire metadata/jobs/history independently. Files remain until expiry so one upload can support several analyses. Back up the Mongo and upload volumes together if retaining data matters.

Endpoints: `GET /api/health` (public readiness); `GET /api/config`; `POST /api/upload-h5ad` (multipart `file`); `POST /api/predict` (`analysis_id`, `smiles`, `organ`; returns HTTP 202 with a job ID); `GET /api/jobs/{job_id}` (queued/running/completed/failed and result); `GET /api/predictions/{analysis_id}` (latest 50). All except health require `X-API-Key`.

## Docker (single trusted operator)

Requires Docker Compose v2 and enough memory/disk for Scanpy, RDKit and MongoDB. CPU PyTorch and PyTorch Geometric are optional and excluded from the default image to limit its size. From the repository root:

```sh
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Generate **two distinct values** with that command and put them in `.env` as `API_KEY` and `MONGO_PASSWORD`. Use URL-safe hex for the Mongo password. Then:

```sh
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8080/api/health
```

Open `http://127.0.0.1:8080` and enter `API_KEY` in the Access form. The web container is exposed only on loopback by default; put a TLS reverse proxy and real identity layer in front before exposing it remotely. The browser holds the key only in session storage; this is a single-operator shared secret, **not** per-user authentication. Never embed the key in the React build. Data stays in Docker volumes; `docker compose down` retains them, while `docker compose down -v` deletes them. Back them up before any destructive operation.

## Local development

Use Python 3.11, Node 20.17+ with npm 11.9.0, a MongoDB 7 instance and adequate RAM. Start MongoDB with `docker compose up -d mongo` after creating `.env`, or supply your own `MONGO_URL`. In one terminal:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
export API_KEY='<your long random API key>'
export MONGO_URL='mongodb://app:<your Mongo password>@localhost:27017/ligand_demo?authSource=admin'
export UPLOAD_DIR='./data/uploads'
uvicorn server:app --app-dir backend --reload --port 8001
```

The Compose Mongo service is deliberately not published. For host-local development, run `docker compose -f compose.yaml -f compose.dev.yaml up -d mongo` to publish it on loopback, or use an existing Mongo instance and its own URL. Do not commit credentials. On Windows PowerShell use `$env:API_KEY='...'`, `$env:MONGO_URL='...'`, and `.venv\Scripts\Activate.ps1` instead of `export` and `source`.

In a second terminal:

```sh
cd frontend
cp .env.example .env.local
npm install -g npm@11.9.0
npm ci
npm start
```

Open `http://localhost:3000`, enter the same API key and upload a dataset. `REACT_APP_BACKEND_URL=http://localhost:8001` is used for separate local servers; the production build uses an empty URL for same-origin nginx. Backend CORS defaults to `http://localhost:3000` and can be changed with `CORS_ORIGINS` (comma-separated exact origins).

To call the API directly:

```sh
curl -H "X-API-Key: $API_KEY" -F 'file=@sample.h5ad' http://localhost:8001/api/upload-h5ad
curl -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"analysis_id":"<id from upload>","smiles":"CC(=O)OC1=CC=CC=C1C(=O)O","organ":"liver"}' \
  http://localhost:8001/api/predict
# Use the returned job_id to poll until status is completed or failed:
curl -H "X-API-Key: $API_KEY" http://localhost:8001/api/jobs/<job_id>
```

The H5AD needs at least two cells and two genes, at most 20,000 cells, 30,000 genes, 20 million matrix entries and a nonnegative finite expression matrix. If `obs['organ']` or `obs['tissue']` is present, only matching cells are analyzed. Without annotations, organ identity is unverified. Numeric values are treated as expression input for library-size normalization and log1p; processed/log-transformed input may yield misleading summaries. No automatic batch correction or cell-type matching is performed.

| Variable | Default | Purpose |
|---|---|---|
| `API_KEY` | required | Shared secret, at least 24 characters |
| `MONGO_PASSWORD` | required by Compose | Mongo initial root password (URL-safe hex) |
| `MONGO_URL` | local Mongo | Backend connection string |
| `DB_NAME` | `ligand_demo` | Metadata database |
| `UPLOAD_DIR` | `./data/uploads` | Private dataset directory |
| `MAX_UPLOAD_MB` | `25` | Upload size cap (1–100) |
| `RETENTION_HOURS` | `24` | Data expiry (1–168) |
| `CORS_ORIGINS` | `http://localhost:3000` | Exact development browser origins |
| `MODEL_CHECKPOINT` | empty | Trusted local trained GNN file; leave empty for baseline-only demo |
| `REACT_APP_BACKEND_URL` | empty | Frontend build-time API origin |

To enable an optional GNN, install CPU PyTorch from the official PyTorch CPU wheel index and then `pip install -r backend/requirements-gnn.txt` in the backend environment (or set `INSTALL_GNN=1` for the CPU backend image), and mount a trusted checkpoint with a local Compose override, with `MODEL_CHECKPOINT` pointing to its container path. A checkpoint must be generated and validated outside this project and have `model_kind='ligand_organ_v1'`, a matching `organ`, `validation_reference`, and `state_dict` compatible with `backend/app/gnn.py`. Its output is an experimental classifier score, **not** binding affinity or gene-level treatment response. Never load an untrusted checkpoint. No pretrained or validated checkpoint is distributed here.

## Tests and deployment limits

```sh
python -m pip install -r backend/requirements-dev.txt
API_KEY=0123456789abcdef0123456789abcdef python -m pytest tests -q
cd frontend && CI=true npm test -- --watch=false
```

CI checks Python tests and the React test/build. The application is intended for a small trusted single-operator deployment. The shared API key is not per-user authentication; add an identity layer before remote multi-user access. In-memory API throttling assumes one backend process; nginx also enforces per-IP rate limits. Uploads are capped at 25 MB by default (configurable), and the Mongo-backed queue processes one analysis at a time. Mongo and uploads need coordinated backups; expired files can remain for up to 10 minutes after their deadline. The embedded worker keeps web deployment simple, but sustained multi-user traffic needs separate workers, monitoring, and capacity planning. Genuine ligand effect prediction requires matched perturbation controls and a validated model trained on relevant organ/cell types; accurate binding scores require a specified target and validation data.
