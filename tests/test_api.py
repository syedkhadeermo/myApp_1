import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anndata as ad
import httpx
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'backend'))
os.environ.setdefault('API_KEY', '0123456789abcdef0123456789abcdef')
from app.api import create_app
from app.config import Settings
from app.storage import cleanup_expired_files
from app.jobs import process_next_job

KEY = '0123456789abcdef0123456789abcdef'


def matches(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if '$gt' in expected and not (actual > expected['$gt']): return False
            if '$in' in expected and actual not in expected['$in']: return False
        elif actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, key, direction): self.docs.sort(key=lambda d: d[key], reverse=direction == -1); return self
    def limit(self, n): self.docs = self.docs[:n]; return self
    def __aiter__(self): self.iter = iter(self.docs); return self
    async def __anext__(self):
        try: return next(self.iter)
        except StopIteration: raise StopAsyncIteration


class Collection:
    def __init__(self): self.docs = []
    async def create_index(self, *args, **kwargs): return None
    async def insert_one(self, doc): self.docs.append(doc); return None
    async def find_one(self, query): return next((d for d in self.docs if matches(d, query)), None)
    async def count_documents(self, query): return sum(matches(d, query) for d in self.docs)
    async def find_one_and_update(self, query, change, sort=None, return_document=None):
        candidates = [d for d in self.docs if matches(d, query)]
        if not candidates: return None
        if sort: candidates.sort(key=lambda d: d[sort[0][0]])
        candidates[0].update(change['$set'])
        return candidates[0]
    async def update_one(self, query, change, upsert=False):
        doc = await self.find_one(query)
        if doc is None and upsert:
            self.docs.append(change['$setOnInsert'])
        elif doc is not None:
            doc.update(change.get('$set', {}))
    async def update_many(self, query, change):
        for d in self.docs:
            if matches(d, query): d.update(change['$set'])
    def find(self, query): return Cursor([d for d in self.docs if matches(d, query)])


class Database:
    def __init__(self): self.analyses = Collection(); self.predictions = Collection(); self.jobs = Collection()
    async def command(self, name): return {'ok': 1}


@pytest.fixture
def client(tmp_path):
    settings = Settings('mongodb://unused', 'test', KEY, tmp_path, 1, 24, ('http://localhost:3000',), '')
    return create_app(settings, Database())


@pytest.mark.asyncio
async def test_upload_predict_queue_history_and_auth(client, tmp_path):
    async with client.router.lifespan_context(client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client), base_url='http://test') as http:
            assert (await http.get('/api/config')).status_code == 401
            headers = {'X-API-Key': KEY}
            assert (await http.get('/api/health')).json()['worker'] == 'running'
            invalid = await http.post('/api/upload-h5ad', files={'file': ('bad.h5ad', b'fake')}, headers=headers)
            assert invalid.status_code == 400
            assert list(tmp_path.glob('*.h5ad')) == []
            data = ad.AnnData(X=np.array([[0, 5], [3, 4], [1, 2]], dtype=float))
            data.var_names = ['GENE1', 'GENE2']
            path = tmp_path / 'fixture.tmp'
            data.write_h5ad(path)
            uploaded = await http.post('/api/upload-h5ad', files={'file': ('test.h5ad', path.read_bytes())}, headers=headers)
            assert uploaded.status_code == 201, uploaded.text
            analysis_id = uploaded.json()['analysis_id']
            payload = {'analysis_id': analysis_id, 'smiles': 'bad!', 'organ': 'liver'}
            assert (await http.post('/api/predict', json=payload, headers=headers)).status_code == 422
            payload['smiles'] = 'CCO'
            queued = await http.post('/api/predict', json=payload, headers=headers)
            assert queued.status_code == 202, queued.text
            job_id = queued.json()['job_id']
            for _ in range(60):
                status = (await http.get(f'/api/jobs/{job_id}', headers=headers)).json()
                if status['status'] in ('completed', 'failed'): break
                await asyncio.sleep(0.05)
            assert status['status'] == 'completed', status
            assert status['result']['binding_score'] is None
            assert status['result']['genes']
            history = await http.get(f'/api/predictions/{analysis_id}', headers=headers)
            assert len(history.json()) == 1
            assert history.json()[0]['id'] == job_id


@pytest.mark.asyncio
async def test_size_limit_cleans_file(client, tmp_path):
    async with client.router.lifespan_context(client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client), base_url='http://test') as http:
            result = await http.post('/api/upload-h5ad', files={'file': ('large.h5ad', b'x' * (1024 * 1024 + 1))}, headers={'X-API-Key': KEY})
            assert result.status_code == 413
            assert not list(tmp_path.glob('*.h5ad'))


def test_retention_sweep_removes_only_expired_h5ad(client, tmp_path):
    old = tmp_path / 'old.h5ad'
    fresh = tmp_path / 'new.h5ad'
    unrelated = tmp_path / 'notes.txt'
    for path in (old, fresh, unrelated): path.write_bytes(b'x')
    stale = time.time() - 25 * 3600
    os.utime(old, (stale, stale))
    cleanup_expired_files(client.state.settings)
    assert not old.exists() and fresh.exists() and unrelated.exists()

@pytest.mark.asyncio
async def test_queue_reports_invalid_organ_annotation(client, tmp_path):
    async with client.router.lifespan_context(client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client), base_url='http://test') as http:
            headers = {'X-API-Key': KEY}
            data = ad.AnnData(X=np.array([[1, 2], [2, 3]], dtype=float))
            data.obs['organ'] = ['liver', 'liver']
            path = tmp_path / 'annotated.tmp'
            data.write_h5ad(path)
            uploaded = await http.post('/api/upload-h5ad', files={'file': ('annotated.h5ad', path.read_bytes())}, headers=headers)
            analysis_id = uploaded.json()['analysis_id']
            queued = await http.post('/api/predict', json={'analysis_id': analysis_id, 'smiles': 'CCO', 'organ': 'lung'}, headers=headers)
            job_id = queued.json()['job_id']
            for _ in range(60):
                state = (await http.get(f'/api/jobs/{job_id}', headers=headers)).json()
                if state['status'] == 'failed': break
                await asyncio.sleep(0.05)
            assert state['status'] == 'failed'
            assert 'No cells annotated' in state['error']
            assert (await http.get(f'/api/predictions/{analysis_id}', headers=headers)).json() == []

@pytest.mark.asyncio
async def test_retention_timer_sweeps_without_new_upload(client, tmp_path, monkeypatch):
    from app import storage
    old = tmp_path / 'timer.h5ad'
    old.write_bytes(b'x')
    stale = time.time() - 25 * 3600
    os.utime(old, (stale, stale))
    monkeypatch.setattr(storage, 'CLEANUP_INTERVAL_SECONDS', 0.01)
    task = asyncio.create_task(storage.cleanup_loop(client.state.settings))
    try:
        for _ in range(20):
            if not old.exists(): break
            await asyncio.sleep(0.01)
        assert not old.exists()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_early_content_length_guard(client, tmp_path):
    async with client.router.lifespan_context(client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client), base_url='http://test') as http:
            response = await http.post('/api/upload-h5ad', headers={'X-API-Key': KEY, 'Content-Length': str(3 * 1024 * 1024)}, content=b'')
            assert response.status_code == 413
            assert not list(tmp_path.glob('*.h5ad'))


@pytest.mark.asyncio
async def test_job_claims_oldest_and_recovers_running_on_restart(client, tmp_path, monkeypatch):
    from app import api as api_module
    db = client.state.db
    now = datetime.now(timezone.utc)
    ids = ['00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002']
    for i, job_id in enumerate(ids):
        await db.jobs.insert_one({'job_id': job_id, 'analysis_id': job_id, 'smiles': 'CCO', 'organ': 'liver',
                                  'status': 'running' if i == 0 else 'queued', 'created_at': now, 'expires_at': now.replace(year=now.year + 1)})
    hold = asyncio.Event()
    async def paused_worker(*args):
        await hold.wait()
    monkeypatch.setattr(api_module, 'worker_loop', paused_worker)
    async with client.router.lifespan_context(client):
        assert [j['status'] for j in db.jobs.docs] == ['queued', 'queued']
        # The oldest queued job is claimed, then marked failed when its dataset is unavailable.
        assert await process_next_job(db, client.state.settings) is True
        assert [j['status'] for j in db.jobs.docs] == ['failed', 'queued']
        assert await process_next_job(db, client.state.settings) is True
        assert await process_next_job(db, client.state.settings) is False
