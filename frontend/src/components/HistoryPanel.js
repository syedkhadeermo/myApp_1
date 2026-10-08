import React from 'react';
export default function HistoryPanel({ items, onSelect }) {
  if (!items.length) return null;
  return <section className="panel" aria-labelledby="history-title"><h2 id="history-title">Recent analyses</h2>
    <p>Saved in MongoDB for this upload until its retention period ends.</p>
    <ul className="history">{items.map(item => <li key={item.id}><button className="secondary" onClick={() => onSelect(item)}><strong>{item.organ}</strong> · {new Date(item.timestamp).toLocaleString()} · <code>{item.smiles}</code></button></li>)}</ul>
  </section>;
}
