const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');

export async function api(path, key, options = {}) {
  const response = await fetch(`${base}/api${path}`, {
    ...options,
    headers: { 'X-API-Key': key, ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`);
  }
  return body;
}
