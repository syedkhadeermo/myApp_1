import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'backend'))
from app.science import inspect_dataset, summarize, validate_smiles, optional_gnn_score


def test_baseline_ranking_is_deterministic_and_organ_filtered(tmp_path):
    data = ad.AnnData(X=np.array([[0, 2, 3], [0, 4, 2], [10, 1, 0]], dtype=float))
    data.var_names = ['A', 'B', 'C']
    data.obs['organ'] = ['liver', 'liver', 'lung']
    path = tmp_path / 'small.h5ad'
    data.write_h5ad(path)
    assert inspect_dataset(path) == (3, 3)
    first = summarize(path, 'liver')
    assert first == summarize(path, 'liver')
    assert first['n_cells_used'] == 2 and first['organ_verified']
    with pytest.raises(ValueError, match='No cells annotated'):
        summarize(path, 'kidney')


def test_smiles_validation_and_no_untrained_model():
    canonical, molecule = validate_smiles('CCO')
    assert canonical == 'CCO'
    assert optional_gnn_score(molecule, 'liver', '') is None
    for value in ('not-a-smiles', '', 'C' * 301):
        with pytest.raises(ValueError):
            validate_smiles(value)


def test_shape_limit(tmp_path):
    data = ad.AnnData(X=np.zeros((2, 30001), dtype=np.float32))
    path = tmp_path / 'wide.h5ad'
    data.write_h5ad(path)
    with pytest.raises(ValueError, match='Dataset needs'):
        inspect_dataset(path)
