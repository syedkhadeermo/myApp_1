"""Exploratory expression summaries. No treatment or binding claims."""
import math
from pathlib import Path
import h5py
import numpy as np
import scanpy as sc
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors
from scipy import sparse

RDLogger.DisableLog('rdApp.error')  # Invalid confidential SMILES must not enter server logs.

MAX_CELLS, MAX_GENES, MAX_ELEMENTS = 20_000, 30_000, 20_000_000
MAX_DENSE_WORKING_BYTES = 512 * 1024 * 1024
ORGANS = ('liver', 'lung', 'heart', 'brain', 'kidney', 'muscle', 'bone', 'skin', 'pancreas', 'stomach')
CONTEXT = {
    'liver': ['hepatitis', 'cirrhosis'], 'lung': ['asthma', 'COPD'],
    'heart': ['heart failure'], 'brain': ['neurodegenerative disease'],
    'kidney': ['chronic kidney disease'], 'muscle': ['myopathy'],
    'bone': ['osteoporosis'], 'skin': ['psoriasis'],
    'pancreas': ['diabetes'], 'stomach': ['gastritis'],
}

def validate_smiles(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 300:
        raise ValueError('SMILES must contain 1–300 characters')
    mol = Chem.MolFromSmiles(value)
    if mol is None or mol.GetNumHeavyAtoms() > 100:
        raise ValueError('Invalid SMILES or more than 100 heavy atoms')
    return Chem.MolToSmiles(mol), mol

def inspect_dataset(path):
    adata = sc.read_h5ad(path, backed='r')
    try:
        n, g = adata.shape
        if n < 2 or g < 2 or n > MAX_CELLS or g > MAX_GENES or n * g > MAX_ELEMENTS:
            raise ValueError(f'Dataset needs 2–{MAX_CELLS} cells, 2–{MAX_GENES} genes, and at most {MAX_ELEMENTS} entries')
        # Scanpy normalization and ranking make multiple dense arrays. Check the
        # on-disk dtype before reading X into memory; sparse storage stays sparse.
        if isinstance(adata.X, h5py.Dataset) and n * g * max(adata.X.dtype.itemsize, 8) * 4 > MAX_DENSE_WORKING_BYTES:
            raise ValueError('Dense expression matrix is too large for this demo; use a smaller or sparse H5AD')
        return int(n), int(g)
    finally:
        adata.file.close()

def summarize(path, organ):
    inspect_dataset(path)
    adata = sc.read_h5ad(path)
    if not adata.var_names.is_unique:
        adata.var_names_make_unique()
    matched = False
    for column in ('organ', 'tissue'):
        if column in adata.obs:
            labels = adata.obs[column].astype(str).str.lower().str.strip()
            mask = np.asarray(labels == organ)
            if not mask.any():
                raise ValueError(f"No cells annotated as {organ} in obs['{column}']")
            adata = adata[mask].copy()
            matched = True
            break
    if adata.n_obs < 2:
        raise ValueError('At least two cells from the chosen organ are required')
    matrix = adata.X
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError('Expression matrix contains negative or non-finite values')
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    x = adata.X
    mean = np.asarray(x.mean(axis=0)).ravel()
    squared = np.asarray(x.multiply(x).mean(axis=0)).ravel() if sparse.issparse(x) else np.mean(np.square(x), axis=0)
    variance = np.maximum(squared - mean * mean, 0)
    detected = np.asarray((x > 0).mean(axis=0)).ravel()
    ranking = variance * np.sqrt(detected)
    indices = sorted(range(adata.n_vars), key=lambda i: (-ranking[i], str(adata.var_names[i])))[:10]
    return {
        'genes': [{'gene': str(adata.var_names[i]), 'variability': round(float(ranking[i]), 5), 'detection_fraction': round(float(detected[i]), 4)} for i in indices],
        'n_cells_used': int(adata.n_obs), 'organ_verified': matched,
    }

def molecular_profile(mol):
    return {'molecular_weight': round(Descriptors.MolWt(mol), 2), 'logp': round(Descriptors.MolLogP(mol), 2), 'heavy_atoms': mol.GetNumHeavyAtoms()}

def optional_gnn_score(mol, organ, checkpoint):
    if not checkpoint:
        return None
    import torch
    from torch_geometric.data import Data
    from .gnn import LigandOrganGNN
    if not Path(checkpoint).is_file():
        raise RuntimeError('Configured model checkpoint does not exist')
    # A checkpoint is a trusted local operator asset, never an uploaded file.
    bundle = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if bundle.get('model_kind') != 'ligand_organ_v1' or bundle.get('organ') != organ or not bundle.get('validation_reference'):
        raise RuntimeError('Model checkpoint lacks matching organ or validation metadata')
    model = LigandOrganGNN()
    model.load_state_dict(bundle['state_dict'], strict=True)
    model.eval()
    nodes = [[a.GetAtomicNum() / 100, a.GetDegree() / 4, a.GetFormalCharge() / 4] for a in mol.GetAtoms()]
    edges = [[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] for b in mol.GetBonds()]
    edges += [[v, u] for u, v in edges]
    edge_index = torch.tensor(edges, dtype=torch.long).T.contiguous() if edges else torch.empty((2, 0), dtype=torch.long)
    graph = Data(x=torch.tensor(nodes, dtype=torch.float), edge_index=edge_index, batch=torch.zeros(len(nodes), dtype=torch.long))
    with torch.no_grad():
        score = float(torch.sigmoid(model(graph)).item())
    if not math.isfinite(score):
        raise RuntimeError('Model generated a non-finite score')
    return {'value': round(score, 4), 'model_reference': str(bundle['validation_reference'])}
