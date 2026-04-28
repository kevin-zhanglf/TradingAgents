import yaml
from pathlib import Path
from typing import Dict, Set
from .schema import ChainGraph, ChainNode, ChainEdge


def load_graph(path: str) -> ChainGraph:
    """Load and validate a ChainGraph from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ChainGraph.model_validate(data)


def get_subgraph(graph: ChainGraph, target_grade: str, target_region: str, hops: int = 2) -> ChainGraph:
    """Extract k-hop neighborhood subgraph centered on target_grade."""
    node_map: Dict[str, ChainNode] = {n.id: n for n in graph.nodes}
    adj: Dict[str, Set[str]] = {n.id: set() for n in graph.nodes}
    for edge in graph.edges:
        adj[edge.source].add(edge.target)
        adj[edge.target].add(edge.source)

    visited: Set[str] = set()
    frontier = {target_grade}
    for _ in range(hops):
        next_frontier = set()
        for node_id in frontier:
            if node_id not in visited and node_id in adj:
                visited.add(node_id)
                next_frontier.update(adj[node_id])
        frontier = next_frontier - visited
        visited.update(frontier)

    if target_grade not in visited:
        visited.add(target_grade)

    sub_nodes = [n for n in graph.nodes if n.id in visited]
    sub_edges = [e for e in graph.edges if e.source in visited and e.target in visited]

    return ChainGraph(nodes=sub_nodes, edges=sub_edges)
