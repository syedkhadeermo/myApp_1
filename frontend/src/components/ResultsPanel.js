import React from 'react';
export default function ResultsPanel({ result }) {
  if (!result) return null;
  const max = Math.max(...result.genes.map(g => g.variability), 0.001);
  return <section className="panel" aria-labelledby="results-title">
    <h2 id="results-title">3. Exploratory results</h2>
    <div className="result-interpretation" role="note"><strong>How to read this result</strong><p>{result.interpretation}</p><p>Research demo: no ligand-induced gene effects or cures are simulated.</p></div>
    <p className="organ-status"><strong>Organ annotation:</strong> {result.organ_verified ? `Found matching ${result.organ} cells in the H5AD file.` : `No organ/tissue annotation was found in the H5AD file. These cells are not verified as ${result.organ}.`}</p>
    <div className="metrics">
      <div><strong>Binding score</strong><span>{result.binding_score ?? 'Unavailable'}</span></div>
      <div><strong>GNN ligand–organ score</strong><span>{result.ligand_organ_score?.value ?? 'No trained model'}</span></div>
      <div><strong>Cells used</strong><span>{result.n_cells_used.toLocaleString()}</span></div>
    </div>
    <h3>Top variable expressed genes (baseline)</h3>
    <ol className="bars">{result.genes.map(g => <li key={g.gene}><span className="gene">{g.gene}</span><span className="track"><span style={{ width: `${100 * g.variability / max}%` }} /></span><span>{g.variability.toFixed(3)}</span></li>)}</ol>
    <div className="columns"><div><h3>Protein proxies</h3><p>{result.top_proteins.join(', ') || 'None'}</p></div><div><h3>Organ disease context</h3><p>{result.related_diseases.join(', ')}</p></div></div>
    <p className="meta">SMILES: <code>{result.smiles}</code> · MW {result.molecular_profile.molecular_weight} · logP {result.molecular_profile.logp}</p>
  </section>;
}
