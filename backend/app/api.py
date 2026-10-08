"""Single-operator API. Uploaded data stays in a bounded private volume."""
import asyncio
import hashlib
import hmac
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .science import ORGANS, inspect_dataset, validate_smiles
from .jobs import worker_loop
from .storage import cleanup_expired_files, cleanup_loop

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(name)s %(message)s')
HDF5_MAGIC = b'\x89HDF\r\n\x1a\n'

class PredictionRequest(BaseModel):
    analysis_id: uuid.UUID
    smiles: str = Field(min_length=1, max_length=300)
    organ: str

class PredictionResponse(BaseModel):
    id: str
    analysis_id: str
    smiles: str
    organ: str
    timestamp: datetime
    genes: list[dict]
    top_proteins: list[str]
    related_diseases: list[str]
    binding_score: None = None
    ligand_organ_score: dict | None = None
    molecular_profile: dict
    n_cells_used: int
    organ_verified: bool
    interpretation: str


def create_app(settings: Settings | None = None, db=None):
    settings = settings or Settings.from_env()
    if not 1 <= settings.max_upload_mb <= 100 or not 1 <= settings.retention_hours <= 168:
        raise ValueError('MAX_UPLOAD_MB must be 1–100 and RETENTION_HOURS 1–168')
    mongo = None
    @asynccontextmanager
    async def lifespan(app):
        nonlocal mongo
        settings.upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if db is None:
            mongo = AsyncIOMotorClient(settings.mongo_url, serverSelectionTimeoutMS=5000)
            app.state.db = mongo[settings.db_name]
        else:
            app.state.db = db
        await app.state.db.command('ping')
        await app.state.db.analyses.create_index('analysis_id', unique=True)
        await app.state.db.analyses.create_index('expires_at', expireAfterSeconds=0)
        await app.state.db.predictions.create_index([('analysis_id', ASCENDING), ('timestamp', DESCENDING)])
        await app.state.db.predictions.create_index('expires_at', expireAfterSeconds=0)
        await app.state.db.predictions.create_index('id', unique=True)
        await app.state.db.jobs.create_index('job_id', unique=True)
        await app.state.db.jobs.create_index([('status', ASCENDING), ('created_at', ASCENDING)])
        await app.state.db.jobs.create_index('expires_at', expireAfterSeconds=0)
        # Single worker process: recover a claim interrupted by a restart.
        await app.state.db.jobs.update_many({'status': 'running'}, {'$set': {'status': 'queued'}})
        cleanup_expired_files(settings)
        app.state.worker = asyncio.create_task(worker_loop(app.state.db, settings))
        app.state.cleanup_task = asyncio.create_task(cleanup_loop(settings))
        try:
            yield
        finally:
            app.state.worker.cancel()
            app.state.cleanup_task.cancel()
            await asyncio.gather(app.state.worker, app.state.cleanup_task, return_exceptions=True)
            if mongo is not None:
                mongo.close()
    app = FastAPI(title='scRNA-seq Ligand Exploration', version='1.0.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=['GET', 'POST'], allow_headers=['X-API-Key', 'Content-Type'], allow_credentials=False)
    app.state.db = db
    app.state.settings = settings
    app.state.bucket = {}
    async def authorize(request: Request, x_api_key: str | None = Header(default=None)):
        if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(401, 'Valid X-API-Key required')
        now = time.monotonic()
        # Single-process, single-key throttle; nginx also enforces per-IP request limits.
        bucket = request.app.state.bucket
        events = [t for t in bucket.get('calls', []) if now - t < 60]
        if len(events) >= 60:
            raise HTTPException(429, 'Rate limit exceeded; retry in one minute')
        events.append(now)
        bucket['calls'] = events

    @app.get('/api/health')
    async def health(request: Request):
        try:
            await request.app.state.db.command('ping')
            if request.app.state.worker.done():
                raise RuntimeError('Job worker stopped')
            return {'status': 'ok', 'database': 'connected', 'worker': 'running', 'model': 'configured' if settings.model_checkpoint else 'unavailable'}
        except Exception:
            return JSONResponse(status_code=503, content={'status': 'unavailable', 'database': 'disconnected'})

    @app.get('/api/config', dependencies=[Depends(authorize)])
    async def config():
        return {'organs': ORGANS, 'max_upload_mb': settings.max_upload_mb, 'retention_hours': settings.retention_hours}

    @app.post('/api/upload-h5ad', dependencies=[Depends(authorize)], status_code=201)
    async def upload(file: UploadFile = File(...)):
        if not file.filename or not file.filename.lower().endswith('.h5ad'):
            raise HTTPException(400, 'Upload a .h5ad file')
        cleanup_expired_files(settings)
        analysis_id = str(uuid.uuid4())
        path = settings.upload_dir / f'{analysis_id}.h5ad'
        size, digest = 0, hashlib.sha256()
        try:
            with path.open('xb') as output:
                os.chmod(path, 0o600)
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, f'File exceeds {settings.max_upload_mb} MB limit')
                    digest.update(chunk)
                    output.write(chunk)
            with path.open('rb') as check_file:
                magic = check_file.read(8)
            if size < 8 or magic != HDF5_MAGIC:
                raise HTTPException(400, 'File is not HDF5/H5AD')
            try:
                cells, genes = await run_in_threadpool(inspect_dataset, path)
            except Exception as exc:
                log.warning('Rejected H5AD: %s', type(exc).__name__)
                raise HTTPException(400, f'Invalid or unsupported H5AD: {str(exc)[:180]}') from exc
            now = datetime.now(timezone.utc)
            await app.state.db.analyses.insert_one({
                'analysis_id': analysis_id, 'filename': Path(file.filename).name[:180],
                'sha256': digest.hexdigest(), 'size_bytes': size,
                'n_cells': cells, 'n_genes': genes, 'created_at': now,
                'expires_at': now + timedelta(hours=settings.retention_hours),
            })
            return {'analysis_id': analysis_id, 'filename': Path(file.filename).name[:180], 'n_cells': cells, 'n_genes': genes, 'expires_at': (now + timedelta(hours=settings.retention_hours)).isoformat()}
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.post('/api/predict', status_code=202, dependencies=[Depends(authorize)])
    async def predict(payload: PredictionRequest):
        organ = payload.organ.strip().lower()
        if organ not in ORGANS:
            raise HTTPException(422, f'Organ must be one of: {", ".join(ORGANS)}')
        try:
            smiles, _ = validate_smiles(payload.smiles.strip())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        record = await app.state.db.analyses.find_one({'analysis_id': str(payload.analysis_id), 'expires_at': {'$gt': datetime.now(timezone.utc)}})
        if record is None:
            raise HTTPException(404, 'Analysis not found or expired; upload again')
        if not (settings.upload_dir / f'{payload.analysis_id}.h5ad').is_file():
            raise HTTPException(410, 'Dataset file unavailable; upload again')
        if await app.state.db.jobs.count_documents({'status': {'$in': ['queued', 'running']}}) >= 20:
            raise HTTPException(429, 'Analysis queue is full; retry later')
        job_id = str(uuid.uuid4())
        await app.state.db.jobs.insert_one({
            'job_id': job_id, 'analysis_id': str(payload.analysis_id),
            'smiles': smiles, 'organ': organ, 'status': 'queued',
            'created_at': datetime.now(timezone.utc), 'expires_at': record['expires_at'],
        })
        return {'job_id': job_id, 'status': 'queued'}

    @app.get('/api/jobs/{job_id}', dependencies=[Depends(authorize)])
    async def job_status(job_id: uuid.UUID):
        job = await app.state.db.jobs.find_one({'job_id': str(job_id), 'expires_at': {'$gt': datetime.now(timezone.utc)}})
        if job is None:
            raise HTTPException(404, 'Job not found or expired')
        answer = {'job_id': str(job_id), 'status': job['status']}
        if job['status'] == 'failed':
            answer['error'] = job.get('error', 'Analysis failed')
        if job['status'] == 'completed':
            result = await app.state.db.predictions.find_one({'id': str(job_id)})
            if result is None:
                raise HTTPException(503, 'Result is not available yet; retry shortly')
            answer['result'] = PredictionResponse.model_validate(result).model_dump(mode='json')
        return answer

    @app.get('/api/predictions/{analysis_id}', response_model=list[PredictionResponse], dependencies=[Depends(authorize)])
    async def history(analysis_id: uuid.UUID):
        record = await app.state.db.analyses.find_one({'analysis_id': str(analysis_id), 'expires_at': {'$gt': datetime.now(timezone.utc)}})
        if record is None:
            raise HTTPException(404, 'Analysis not found or expired')
        cursor = app.state.db.predictions.find({'analysis_id': str(analysis_id)}).sort('timestamp', -1).limit(50)
        return [PredictionResponse.model_validate(p) async for p in cursor]

    return app

app = create_app()
