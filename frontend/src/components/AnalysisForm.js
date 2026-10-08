import React, { useState } from 'react';
const examples = [
  ['Aspirin', 'CC(=O)OC1=CC=CC=C1C(=O)O'],
  ['Caffeine', 'Cn1c(=O)c2c(ncn2C)n(C)c1=O'],
];
export default function AnalysisForm({ onPredict, busy, analysis, organs }) {
  const [smiles, setSmiles] = useState('');
  const [organ, setOrgan] = useState('');
  return <section className="panel" aria-labelledby="analysis-title">
    <h2 id="analysis-title">2. Explore ligand and organ</h2>
    <p>{analysis.filename}: {analysis.n_cells.toLocaleString()} cells, {analysis.n_genes.toLocaleString()} genes.</p>
    <form onSubmit={e => { e.preventDefault(); onPredict({ analysis_id: analysis.analysis_id, smiles, organ }); }}>
      <label htmlFor="smiles">Ligand SMILES</label>
      <input id="smiles" value={smiles} onChange={e => setSmiles(e.target.value)} required maxLength={300} placeholder="e.g. CC(=O)OC1=CC=CC=C1C(=O)O" />
      <div className="examples">Examples: {examples.map(([name, value]) => <button className="secondary" type="button" key={name} onClick={() => setSmiles(value)}>{name}</button>)}</div>
      <label htmlFor="organ">Target organ</label>
      <select id="organ" value={organ} onChange={e => setOrgan(e.target.value)} required><option value="">Select organ</option>{organs.map(o => <option key={o} value={o}>{o}</option>)}</select>
      <button disabled={busy}>{busy ? 'Analyzing…' : 'Run exploratory analysis'}</button>
    </form>
  </section>;
}
