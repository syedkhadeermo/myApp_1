import sys
from pathlib import Path
from datetime import datetime, timezone

import anndata as ad
import httpx
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'backend'))
# import only after key is present because the deployed module constructs its app
import os
os.environ.setdefault('API_KEY', '0123456789abcdef0123456789abcdef')
from app.api import create_app
from app.config import Settings

KEY = '0123456789abcdef0123456789abcdef'

class Cursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, key, direction): return self
    def limit(self, n): self.docs = self.docs[:n]; return self
    def __aiter__(self): self.iter = iter(self.docs); return self
    async def __anext__(self):
        try: return next(self.iter)
        except StopIteration: raise StopAsyncIteration

class Collection:
    def __init__(self): self.docs = []
    async def create_index(self, *args, **kwargs): return None
    async def insert_one(self, doc): self.docs.append(doc); return None
    async def find_one(self, query):
        for doc in self.docs:
            if doc['analysis_id'] == query['analysis_id'] and doc.get('expires_at', datetime.max.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc): return doc
        return None
    def find(self, query): return Cursor([d for d in self.docs if d['analysis_id'] == query['analysis_id']][::-1])

class Database:
    def __init__(self): self.analyses = Collection(); self.predictions = Collection()
    async def command(self, name): return {'ok': 1}

@pytest.fixture
def client(tmp_path):
    settings = Settings('mongodb://unused', 'test', KEY, tmp_path, 1, 24, ('http://localhost:3000',), '')
    app = create_app(settings, Database())
    return app

@pytest.mark.asyncio
async def test_upload_predict_history_and_auth(client, tmp_path):
    async with client.router.lifespan_context(client):
        transport = httpx.ASGITransport(app=client)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as http:
            assert (await http.get('/api/config')).status_code == 401
            headers = {'X-API-Key': KEY}
            assert (await http.get('/api/health')).json()['status'] == 'ok'
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
            bad = await http.post('/api/predict', json={'analysis_id': analysis_id, 'smiles': 'bad!', 'organ': 'liver'}, headers=headers)
            assert bad.status_code == 422
            response = await http.post('/api/predict', json={'analysis_id': analysis_id, 'smiles': 'CCO', 'organ': 'liver'}, headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()['binding_score'] is None
            assert response.json()['genes']
            history = await http.get(f'/api/predictions/{analysis_id}', headers=headers)
            assert len(history.json()) == 1

@pytest.mark.asyncio
async def test_size_limit_cleans_file(client, tmp_path):
    async with client.router.lifespan_context(client):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client), base_url='http://test') as http:
            result = await http.post('/api/upload-h5ad', files={'file': ('large.h5ad', b'x' * (1024 * 1024 + 1))}, headers={'X-API-Key': KEY})
            assert result.status_code == 413
            assert not list(tmp_path.glob('*.h5ad'))
