import React, { useState } from 'react';

export default function UploadPanel({ onUpload, busy, maxMb }) {
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState(null);
  return <section className="panel" aria-labelledby="upload-title">
    <h2 id="upload-title">1. Upload single-cell data</h2>
    <p>Choose an H5AD file up to {maxMb} MB. Data is retained for a limited time.</p>
    <label className={`drop ${drag ? 'drag' : ''}`} onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); setFile(e.dataTransfer.files[0] || null); }}>
      <input type="file" accept=".h5ad" onChange={e => setFile(e.target.files[0] || null)} />
      <span>{file ? file.name : 'Select or drop an .h5ad file'}</span>
    </label>
    <button type="button" disabled={!file || busy} onClick={() => onUpload(file)}>{busy ? 'Uploading and checking…' : 'Upload data'}</button>
  </section>;
}
