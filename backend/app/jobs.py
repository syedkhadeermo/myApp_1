"""Small durable Mongo queue for one API/worker process."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from pymongo import ASCENDING, ReturnDocument
from starlette.concurrency import run_in_threadpool

from .science import CONTEXT, molecular_profile, optional_gnn_score, summarize, validate_smiles

log = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


async def process_next_job(db, settings):
    """Atomically claim one job. Returns False when the queue is empty."""
    job = await db.jobs.find_one_and_update(
        {'status': 'queued', 'expires_at': {'$gt': utcnow()}},
        {'$set': {'status': 'running', 'started_at': utcnow()}},
        sort=[('created_at', ASCENDING)], return_document=ReturnDocument.AFTER,
    )
    if job is None:
        return False
    try:
        record = await db.analyses.find_one({'analysis_id': job['analysis_id'], 'expires_at': {'$gt': utcnow()}})
        path = settings.upload_dir / f"{uuid.UUID(job['analysis_id'])}.h5ad"
        if record is None or not path.is_file():
            raise ValueError('Dataset expired or unavailable; upload again')
        _, mol = validate_smiles(job['smiles'])
        summary = await run_in_threadpool(summarize, path, job['organ'])
        gnn = await run_in_threadpool(optional_gnn_score, mol, job['organ'], settings.model_checkpoint)
        result = {
            'id': job['job_id'], 'analysis_id': job['analysis_id'],
            'smiles': job['smiles'], 'organ': job['organ'], 'timestamp': utcnow(),
            'genes': summary['genes'],
            'top_proteins': [g['gene'] for g in summary['genes'][:5]],
            'related_diseases': CONTEXT[job['organ']], 'binding_score': None,
            'ligand_organ_score': gnn, 'molecular_profile': molecular_profile(mol),
            'n_cells_used': summary['n_cells_used'], 'organ_verified': summary['organ_verified'],
            'interpretation': 'Genes are ranked by baseline expression variability, not ligand response. Protein names are gene-symbol proxies. Disease names are organ context, not predicted cures. Binding requires a protein target and validated assay/model.',
            'expires_at': record['expires_at'],
        }
        # Same job ID is the result ID, so restart recovery cannot duplicate history.
        await db.predictions.update_one({'id': job['job_id']}, {'$setOnInsert': result}, upsert=True)
        await db.jobs.update_one({'job_id': job['job_id']}, {'$set': {'status': 'completed', 'completed_at': utcnow()}})
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning('Analysis job %s failed (%s)', job['job_id'], type(exc).__name__)
        message = str(exc) if isinstance(exc, ValueError) else 'Analysis unavailable; check dataset and model configuration'
        await db.jobs.update_one({'job_id': job['job_id']}, {'$set': {'status': 'failed', 'error': message[:180], 'completed_at': utcnow()}})
    return True


async def worker_loop(db, settings):
    while True:
        try:
            processed = await process_next_job(db, settings)
            if not processed:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Job worker failed to poll MongoDB')
            await asyncio.sleep(5)
