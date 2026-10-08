import { api } from './api';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import App from './App';
jest.mock('./api', () => ({ api: jest.fn() }));

test('API sends the session key and explains server errors', async () => {
  const realApi = jest.requireActual('./api').api;
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: 'Invalid SMILES' }) });
  await expect(realApi('/predict', 'demo-key')).rejects.toThrow('Invalid SMILES');
  expect(global.fetch).toHaveBeenCalledWith('/api/predict', expect.objectContaining({ headers: expect.objectContaining({ 'X-API-Key': 'demo-key' }) }));
});

const analysis = { analysis_id: 'dataset-1', filename: 'test.h5ad', n_cells: 2, n_genes: 2 };
const result = { id: 'job-1', analysis_id: analysis.analysis_id, organ: 'liver', smiles: 'CCO',
  timestamp: '2026-10-08T00:00:00Z', genes: [{ gene: 'A', variability: 1 }],
  interpretation: 'Baseline expression only.', binding_score: null, ligand_organ_score: null,
  n_cells_used: 2, organ_verified: false, top_proteins: ['A'], related_diseases: ['hepatitis'],
  molecular_profile: { molecular_weight: 46, logp: 0 } };

async function renderPending(statuses) {
  sessionStorage.setItem('apiKey', 'demo-key');
  sessionStorage.setItem('analysis', JSON.stringify(analysis));
  sessionStorage.setItem('pendingJob', JSON.stringify({ job_id: 'job-1', status: 'queued', analysis_id: analysis.analysis_id }));
  const nextStatus = jest.fn().mockImplementation(() => Promise.resolve(statuses.shift()));
  api.mockImplementation(path => {
    if (path === '/config') return Promise.resolve({ organs: ['liver'], max_upload_mb: 25 });
    if (path === `/predictions/${analysis.analysis_id}`) return Promise.resolve([]);
    if (path === '/jobs/job-1') return nextStatus();
    throw new Error(`Unexpected request ${path}`);
  });
  const node = document.createElement('div');
  document.body.appendChild(node);
  const root = createRoot(node);
  await act(async () => { root.render(<App />); });
  return { node, root, nextStatus };
}

describe('job polling after a page reload', () => {
  beforeEach(() => { jest.useFakeTimers(); sessionStorage.clear(); api.mockReset(); global.IS_REACT_ACT_ENVIRONMENT = true; });
  afterEach(() => { jest.useRealTimers(); sessionStorage.clear(); });

  test('moves queued to running to completed and clears the pending job', async () => {
    const { node, root, nextStatus } = await renderPending([{ status: 'queued' }, { status: 'running' }, { status: 'completed', result }]);
    for (const [delay, label] of [[250, 'queued'], [1500, 'running']]) {
      await act(async () => { jest.advanceTimersByTime(delay); });
      expect(node.querySelector('[role="status"]').textContent).toContain(label);
    }
    await act(async () => { jest.advanceTimersByTime(1500); });
    expect(nextStatus).toHaveBeenCalledTimes(3);
    expect(node.textContent).toContain('How to read this result');
    expect(node.textContent).toContain('No organ/tissue annotation was found');
    expect(sessionStorage.getItem('pendingJob')).toBeNull();
    await act(async () => root.unmount()); node.remove();
  });

  test('shows a failed job and clears pending state', async () => {
    const { node, root } = await renderPending([{ status: 'failed', error: 'Dataset expired' }]);
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(node.querySelector('[role="alert"]').textContent).toContain('Dataset expired');
    expect(sessionStorage.getItem('pendingJob')).toBeNull();
    await act(async () => root.unmount()); node.remove();
  });
});
