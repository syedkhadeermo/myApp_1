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
from .science import CONTEXT, ORGANS, inspect_dataset, molecular_profile, optional_gnn_score, summarize, validate_smiles

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
        await cleanup(app)
        try:
            yield
        finally:
            if mongo is not None:
                mongo.close()
    app = FastAPI(title='scRNA-seq Ligand Exploration', version='1.0.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=['GET', 'POST'], allow_headers=['X-API-Key', 'Content-Type'], allow_credentials=False)
    app.state.db = db
    app.state.settings = settings
    app.state.bucket = {}
    app.state.analysis_lock = asyncio.Lock()

    async def cleanup(app):
        # TTL indexes delete metadata independently; sweep old files by mtime on startup and upload.
        cutoff = time.time() - settings.retention_hours * 3600
        for path in settings.upload_dir.glob('*.h5ad'):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                log.exception('Could not clean expired upload')

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
            return {'status': 'ok', 'database': 'connected', 'model': 'configured' if settings.model_checkpoint else 'unavailable'}
        except Exception:
            return JSONResponse(status_code=503, content={'status': 'unavailable', 'database': 'disconnected'})

    @app.get('/api/config', dependencies=[Depends(authorize)])
    async def config():
        return {'organs': ORGANS, 'max_upload_mb': settings.max_upload_mb, 'retention_hours': settings.retention_hours}

    @app.post('/api/upload-h5ad', dependencies=[Depends(authorize)], status_code=201)
    async def upload(file: UploadFile = File(...)):
        if not file.filename or not file.filename.lower().endswith('.h5ad'):
            raise HTTPException(400, 'Upload a .h5ad file')
        await cleanup(app)
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

    @app.post('/api/predict', response_model=PredictionResponse, dependencies=[Depends(authorize)])
    async def predict(payload: PredictionRequest):
        organ = payload.organ.strip().lower()
        if organ not in ORGANS:
            raise HTTPException(422, f'Organ must be one of: {", ".join(ORGANS)}')
        try:
            smiles, mol = validate_smiles(payload.smiles.strip())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        record = await app.state.db.analyses.find_one({'analysis_id': str(payload.analysis_id), 'expires_at': {'$gt': datetime.now(timezone.utc)}})
        if record is None:
            raise HTTPException(404, 'Analysis not found or expired; upload again')
        path = settings.upload_dir / f'{payload.analysis_id}.h5ad'
        if not path.is_file():
            raise HTTPException(410, 'Dataset file unavailable; upload again')
        try:
            if app.state.analysis_lock.locked():
                raise HTTPException(429, 'Another analysis is running; retry shortly')
            async with app.state.analysis_lock:
                summary = await run_in_threadpool(summarize, path, organ)
                gnn = await run_in_threadpool(optional_gnn_score, mol, organ, settings.model_checkpoint)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except HTTPException:
            raise
        except Exception:
            log.exception('Scientific analysis failed')
            raise HTTPException(503, 'Scientific analysis unavailable; check dataset and model configuration')
        now = datetime.now(timezone.utc)
        result = PredictionResponse(
            id=str(uuid.uuid4()), analysis_id=str(payload.analysis_id), smiles=smiles,
            organ=organ, timestamp=now, genes=summary['genes'],
            top_proteins=[g['gene'] for g in summary['genes'][:5]],
            related_diseases=CONTEXT[organ], binding_score=None,
            ligand_organ_score=gnn, molecular_profile=molecular_profile(mol),
            n_cells_used=summary['n_cells_used'], organ_verified=summary['organ_verified'],
            interpretation='Genes are ranked by baseline expression variability, not ligand response. Protein names are gene-symbol proxies. Disease names are organ context, not predicted cures. Binding requires a protein target and validated assay/model.',
        )
        await app.state.db.predictions.insert_one({**result.model_dump(mode='python'), 'expires_at': record['expires_at']})
        return result

    @app.get('/api/predictions/{analysis_id}', response_model=list[PredictionResponse], dependencies=[Depends(authorize)])
    async def history(analysis_id: uuid.UUID):
        record = await app.state.db.analyses.find_one({'analysis_id': str(analysis_id), 'expires_at': {'$gt': datetime.now(timezone.utc)}})
        if record is None:
            raise HTTPException(404, 'Analysis not found or expired')
        cursor = app.state.db.predictions.find({'analysis_id': str(analysis_id)}).sort('timestamp', -1).limit(50)
        return [PredictionResponse.model_validate(p) async for p in cursor]

    return app

app = create_app()
