import React, { useEffect, useState } from 'react';
import { api } from './api';
import UploadPanel from './components/UploadPanel';
import AnalysisForm from './components/AnalysisForm';
import ResultsPanel from './components/ResultsPanel';
import HistoryPanel from './components/HistoryPanel';
import './App.css';

export default function App() {
  const [key, setKey] = useState(() => sessionStorage.getItem('apiKey') || '');
  const [draftKey, setDraftKey] = useState(key);
  const [config, setConfig] = useState(null);
  const [analysis, setAnalysis] = useState(() => { try { return JSON.parse(sessionStorage.getItem('analysis') || 'null'); } catch { return null; } });
  const [result, setResult] = useState(null);
  const [job, setJob] = useState(() => { try { return JSON.parse(sessionStorage.getItem('pendingJob') || 'null'); } catch { return null; } });
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (!key) return;
    api('/config', key).then(setConfig).catch(e => { setError(e.message); setConfig(null); });
  }, [key]);
  useEffect(() => {
    if (!key || !analysis) return;
    api(`/predictions/${analysis.analysis_id}`, key).then(setHistory).catch(e => setError(e.message));
  }, [key, analysis]);
  const jobId = job?.job_id;
  useEffect(() => {
    if (!key || !jobId || job.analysis_id !== analysis?.analysis_id) return undefined;
    let active = true;
    let timer;
    async function poll() {
      try {
        const next = await api(`/jobs/${jobId}`, key);
        if (!active) return;
        if (next.status === 'completed') {
          sessionStorage.removeItem('pendingJob');
          setResult(next.result);
          setHistory(old => [next.result, ...old.filter(item => item.id !== next.result.id)]);
          setJob(null);
        } else if (next.status === 'failed') {
          sessionStorage.removeItem('pendingJob');
          setError(next.error || 'Analysis failed');
          setJob(null);
        } else if (next.status === 'queued' || next.status === 'running') {
          setJob(old => old ? { ...old, status: next.status } : null);
          timer = setTimeout(poll, 1500);
        } else {
          throw new Error('Unexpected analysis status; please retry');
        }
      } catch (e) { if (active) { sessionStorage.removeItem('pendingJob'); setError(e.message); setJob(null); } }
    }
    timer = setTimeout(poll, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [key, jobId, job?.analysis_id, analysis?.analysis_id]);
  async function run(name, task) {
    setBusy(name); setError('');
    try { await task(); } catch (e) { setError(e.message || 'Unexpected error'); } finally { setBusy(''); }
  }
  function saveKey(e) { e.preventDefault(); sessionStorage.setItem('apiKey', draftKey); setKey(draftKey); setError(''); }
  function upload(file) { run('upload', async () => {
    if (!file.name.toLowerCase().endsWith('.h5ad')) throw new Error('Select an .h5ad file');
    if (file.size > (config?.max_upload_mb || 25) * 1024 * 1024) throw new Error('File exceeds upload limit');
    const body = new FormData(); body.append('file', file);
    const next = await api('/upload-h5ad', key, { method: 'POST', body });
    sessionStorage.removeItem('pendingJob'); sessionStorage.setItem('analysis', JSON.stringify(next)); setAnalysis(next); setHistory([]); setResult(null); setJob(null);
  }); }
  function predict(payload) { run('predict', async () => {
    const next = await api('/predict', key, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const pending = { ...next, analysis_id: analysis.analysis_id };
    sessionStorage.setItem('pendingJob', JSON.stringify(pending));
    setResult(null); setJob(pending);
  }); }
  function reset() { sessionStorage.removeItem('analysis'); sessionStorage.removeItem('pendingJob'); setAnalysis(null); setResult(null); setHistory([]); setJob(null); setError(''); }
  return <div className="app min-h-screen"><header><div className="wrap mx-auto"><h1>scRNA-seq Ligand Explorer</h1><p>Inspect single-cell expression and ligand structure with honest model limits.</p></div></header>
    <main className="wrap mx-auto">
      <p className="warning">Research demo only. No predicted cures, validated binding affinities, or clinical conclusions.</p>
      <section className="panel access shadow-sm"><h2>Access</h2><form onSubmit={saveKey}><label htmlFor="key">API key</label><input id="key" type="password" autoComplete="off" value={draftKey} onChange={e => setDraftKey(e.target.value)} required placeholder="Enter your deployment API key" /><button>Connect</button></form><small>Key stays in this browser tab’s session storage. Use only on a trusted deployment.</small></section>
      {error && <div className="error" role="alert">{error}</div>}
      {key && config && <>
        {!analysis ? <UploadPanel onUpload={upload} busy={!!busy} maxMb={config.max_upload_mb} /> : <><div className="toolbar"><span>Analysis {analysis.analysis_id}</span><button className="secondary" onClick={reset}>New upload</button></div><AnalysisForm key={analysis.analysis_id} onPredict={predict} busy={!!busy || !!job} analysis={analysis} organs={config.organs} />{job?.analysis_id === analysis.analysis_id && <p className="notice" role="status" aria-live="polite">Analysis {job.status}. You can wait here for the result.</p>}<ResultsPanel result={result} /><HistoryPanel items={history} onSelect={setResult} /></>}
      </>}
    </main></div>;
}
