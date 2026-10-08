"""Architecture for an externally trained ligand–organ demo classifier."""
import torch
from torch_geometric.nn import GCNConv, global_mean_pool

class LigandOrganGNN(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = GCNConv(3, 32)
        self.conv2 = GCNConv(32, 32)
        self.head = torch.nn.Linear(32, 1)

    def forward(self, graph):
        x = self.conv1(graph.x, graph.edge_index).relu()
        x = self.conv2(x, graph.edge_index).relu()
        return self.head(global_mean_pool(x, graph.batch)).squeeze(-1)
