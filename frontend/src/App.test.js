import { api } from './api';

test('API sends the session key and explains server errors', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: 'Invalid SMILES' }) });
  await expect(api('/predict', 'demo-key')).rejects.toThrow('Invalid SMILES');
  expect(global.fetch).toHaveBeenCalledWith('/api/predict', expect.objectContaining({ headers: expect.objectContaining({ 'X-API-Key': 'demo-key' }) }));
});
