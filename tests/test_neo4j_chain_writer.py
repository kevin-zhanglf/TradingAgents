"""Tests for ChainGraphNeo4jWriter (offline – uses a mock Neo4j driver)."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, call

import pytest

from tradingagents.chain_graph.schema import (
    ChainGraph,
    ChainNode,
    ChainEdge,
    NodeType,
    EdgeType,
    PriceSeriesRef,
)


# ---------------------------------------------------------------------------
# Helper: import a module file directly, bypassing package __init__ chains
# ---------------------------------------------------------------------------

def _import_file(module_name: str, filepath: str):
    """Import a .py file as a module without triggering package __init__."""
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Minimal fixture graph
# ---------------------------------------------------------------------------

@pytest.fixture()
def minimal_graph() -> ChainGraph:
    """A tiny two-grade graph that shares upstream nodes."""
    nodes = [
        ChainNode(id="styrene", name="苯乙烯", node_type=NodeType.MONOMER,
                  description="苯乙烯单体"),
        ChainNode(id="abs_polymer", name="ABS树脂", node_type=NodeType.POLYMER,
                  description="ABS聚合物"),
        ChainNode(id="ps_polymer", name="聚苯乙烯", node_type=NodeType.POLYMER,
                  description="PS聚合物"),
        ChainNode(
            id="grade_a",
            name="ABS-GRADE-A",
            node_type=NodeType.GRADE,
            region="华北",
            series=[
                PriceSeriesRef(series_id="grade_a_deal", price_type="deal",
                               region="华北", freq="D", unit="元/吨",
                               tax_included=True, source="卓创资讯")
            ],
        ),
        ChainNode(
            id="grade_b",
            name="ABS-GRADE-B",
            node_type=NodeType.GRADE,
            region="华北",
        ),
        ChainNode(id="home_appliance", name="家电", node_type=NodeType.DOWNSTREAM),
    ]
    edges = [
        ChainEdge(source="styrene", target="abs_polymer",
                  edge_type=EdgeType.UPSTREAM_COST,
                  lag_days=(3, 14), elasticity=0.55, confidence=0.80),
        ChainEdge(source="abs_polymer", target="grade_a",
                  edge_type=EdgeType.SUPPLY_LINK,
                  lag_days=(0, 3), elasticity=0.90, confidence=0.92),
        ChainEdge(source="abs_polymer", target="grade_b",
                  edge_type=EdgeType.SUPPLY_LINK,
                  lag_days=(0, 3), elasticity=0.88, confidence=0.90),
        ChainEdge(source="grade_a", target="ps_polymer",
                  edge_type=EdgeType.SUBSTITUTE,
                  lag_days=(3, 14), elasticity=0.55, confidence=0.70,
                  conditions=["价差超过800元/吨"]),
        ChainEdge(source="grade_a", target="home_appliance",
                  edge_type=EdgeType.DEMAND_LINK,
                  lag_days=(0, 7), elasticity=0.60, confidence=0.75),
    ]
    return ChainGraph(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Mock driver helper
# ---------------------------------------------------------------------------

def _make_mock_driver():
    """Build a mock neo4j driver + session context manager."""
    mock_tx = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute_write = MagicMock(
        side_effect=lambda fn, *args, **kwargs: fn(mock_tx, *args, **kwargs)
    )
    # For get_upstream_chain etc.
    mock_session.run = MagicMock(return_value=iter([]))

    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=mock_session)
    mock_driver.close = MagicMock()
    return mock_driver, mock_session, mock_tx


# ---------------------------------------------------------------------------
# Patching helper: patch neo4j.GraphDatabase at the point used by neo4j_writer
# ---------------------------------------------------------------------------

def _writer_with_mock_driver(mock_driver):
    """Return a ChainGraphNeo4jWriter backed by mock_driver."""
    from tradingagents.chain_graph import neo4j_writer as nw_mod
    with patch.object(nw_mod, "GraphDatabase") as mock_gdb:
        mock_gdb.driver.return_value = mock_driver
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter
        writer = ChainGraphNeo4jWriter(uri="bolt://localhost:7687",
                                       user="neo4j", password="test")
    return writer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChainGraphNeo4jWriterInit:
    def test_import_error_without_neo4j(self):
        """If neo4j package is missing, a clear ImportError is raised."""
        import tradingagents.chain_graph.neo4j_writer as nw_mod
        original = nw_mod._HAS_NEO4J
        try:
            nw_mod._HAS_NEO4J = False
            nw_mod.GraphDatabase = None
            from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter
            with pytest.raises(ImportError, match="neo4j"):
                ChainGraphNeo4jWriter()
        finally:
            nw_mod._HAS_NEO4J = original

    def test_constructor_creates_driver(self):
        from tradingagents.chain_graph import neo4j_writer as nw_mod
        mock_driver, _, _ = _make_mock_driver()
        with patch.object(nw_mod, "GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = mock_driver
            from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter
            writer = ChainGraphNeo4jWriter(uri="bolt://localhost:7687",
                                           user="neo4j", password="pass")
            assert writer._database == "neo4j"
            mock_gdb.driver.assert_called_once()


class TestWriteGraph:
    def test_write_graph_merges_all_nodes_and_edges(self, minimal_graph):
        """write_graph should call execute_write for every node and edge."""
        from tradingagents.chain_graph import neo4j_writer as nw_mod
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_driver, mock_session, mock_tx = _make_mock_driver()
        with patch.object(nw_mod, "GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = mock_driver
            writer = ChainGraphNeo4jWriter(uri="bolt://localhost:7687",
                                           user="neo4j", password="test")
            writer.write_graph(minimal_graph)

        # execute_write: 1 (constraints) + n_nodes + n_edges
        n_nodes = len(minimal_graph.nodes)
        n_edges = len(minimal_graph.edges)
        assert mock_session.execute_write.call_count == 1 + n_nodes + n_edges

    def test_write_graph_with_clear(self, minimal_graph):
        """When clear=True, _clear_graph should be called first."""
        from tradingagents.chain_graph import neo4j_writer as nw_mod
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_driver, mock_session, mock_tx = _make_mock_driver()
        with patch.object(nw_mod, "GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = mock_driver
            writer = ChainGraphNeo4jWriter(uri="bolt://localhost:7687",
                                           user="neo4j", password="test")
            writer.write_graph(minimal_graph, clear=True)

        # execute_write: 1 (clear) + 1 (constraints) + n_nodes + n_edges
        n_nodes = len(minimal_graph.nodes)
        n_edges = len(minimal_graph.edges)
        assert mock_session.execute_write.call_count == 2 + n_nodes + n_edges

    def test_shared_upstream_node_appears_once_in_yaml_graph(self):
        """In the YAML chain graph, styrene is a single node shared by multiple grades.
        This test verifies the YAML loads correctly and the node is not duplicated."""
        from tradingagents.chain_graph.loader import load_graph

        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "tradingagents", "chain_graph", "abs_chain.yaml"
        )
        if not os.path.exists(yaml_path):
            pytest.skip("abs_chain.yaml not found")

        graph = load_graph(yaml_path)
        styrene_nodes = [n for n in graph.nodes if n.id == "styrene"]
        assert len(styrene_nodes) == 1, "styrene should appear exactly once"

    def test_context_manager_closes_driver(self, minimal_graph):
        from tradingagents.chain_graph import neo4j_writer as nw_mod
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_driver, mock_session, mock_tx = _make_mock_driver()
        with patch.object(nw_mod, "GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = mock_driver
            with ChainGraphNeo4jWriter(uri="bolt://localhost:7687",
                                        user="neo4j", password="test") as writer:
                writer.write_graph(minimal_graph)

        mock_driver.close.assert_called_once()


class TestNodeMerge:
    def test_merge_node_cypher_contains_merge(self, minimal_graph):
        """_merge_node should execute a MERGE statement (not CREATE)."""
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_tx = MagicMock()
        node = minimal_graph.nodes[0]  # styrene
        ChainGraphNeo4jWriter._merge_node(mock_tx, node)

        assert mock_tx.run.called
        cypher_call = mock_tx.run.call_args[0][0]
        assert "MERGE" in cypher_call
        assert "id: $id" in cypher_call

    def test_merge_node_sets_correct_label(self, minimal_graph):
        """Grade nodes should get the :Grade label."""
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_tx = MagicMock()
        grade_node = next(n for n in minimal_graph.nodes if n.node_type == NodeType.GRADE)
        ChainGraphNeo4jWriter._merge_node(mock_tx, grade_node)

        cypher_call = mock_tx.run.call_args[0][0]
        assert ":Grade" in cypher_call

    def test_merge_node_serialises_series_as_json(self, minimal_graph):
        """Nodes with price series should store series_json as a string."""
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_tx = MagicMock()
        grade_node = next(n for n in minimal_graph.nodes
                          if n.node_type == NodeType.GRADE and n.series)
        ChainGraphNeo4jWriter._merge_node(mock_tx, grade_node)

        kwargs = mock_tx.run.call_args[1]
        series_json = kwargs["series_json"]
        parsed = json.loads(series_json)
        assert isinstance(parsed, list)
        assert parsed[0]["series_id"] == "grade_a_deal"


class TestEdgeMerge:
    def test_merge_edge_cypher_uses_correct_rel_type(self, minimal_graph):
        """SUBSTITUTE edges should produce [:SUBSTITUTE] in the Cypher."""
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_tx = MagicMock()
        sub_edge = next(e for e in minimal_graph.edges
                        if e.edge_type == EdgeType.SUBSTITUTE)
        ChainGraphNeo4jWriter._merge_edge(mock_tx, sub_edge)

        cypher_call = mock_tx.run.call_args[0][0]
        assert "SUBSTITUTE" in cypher_call
        assert "MERGE" in cypher_call

    def test_merge_edge_stores_lag_days(self, minimal_graph):
        """Lag day min/max should be stored on the relationship."""
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_tx = MagicMock()
        edge = minimal_graph.edges[0]
        ChainGraphNeo4jWriter._merge_edge(mock_tx, edge)

        kwargs = mock_tx.run.call_args[1]
        assert kwargs["lag_min"] == edge.lag_days[0]
        assert kwargs["lag_max"] == edge.lag_days[1]

    def test_merge_edge_stores_conditions(self, minimal_graph):
        """Conditions list should be passed through to the MERGE statement."""
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter

        mock_tx = MagicMock()
        sub_edge = next(e for e in minimal_graph.edges
                        if e.edge_type == EdgeType.SUBSTITUTE)
        ChainGraphNeo4jWriter._merge_edge(mock_tx, sub_edge)

        kwargs = mock_tx.run.call_args[1]
        assert "价差超过800元/吨" in kwargs["conditions"]


class TestRelTypeMapping:
    def test_all_edge_types_have_rel_type_mapping(self):
        """Every EdgeType value must have a mapping in _REL_TYPE."""
        from tradingagents.chain_graph.neo4j_writer import _REL_TYPE

        for et in EdgeType:
            assert et in _REL_TYPE, f"EdgeType.{et} missing from _REL_TYPE"

    def test_all_node_types_have_label_mapping(self):
        """Every NodeType value must have a mapping in _NODE_LABEL."""
        from tradingagents.chain_graph.neo4j_writer import _NODE_LABEL

        for nt in NodeType:
            assert nt in _NODE_LABEL, f"NodeType.{nt} missing from _NODE_LABEL"


class TestChemChainNeo4jTools:
    """Test the LangChain tool wrappers (no real Neo4j needed).

    We import the tools module file directly to avoid triggering the heavy
    ``tradingagents.agents`` package ``__init__`` which pulls in pandas and
    other runtime dependencies not installed in the test environment.
    """

    _TOOLS_PATH = os.path.join(
        os.path.dirname(__file__), "..",
        "tradingagents", "agents", "utils", "chem_chain_neo4j_tools.py"
    )

    def _load_tools(self):
        mod_name = "_test_chem_chain_neo4j_tools"
        if mod_name in sys.modules:
            return sys.modules[mod_name]
        return _import_file(mod_name, self._TOOLS_PATH)

    def test_query_upstream_chain_returns_stub_when_no_env(self):
        """Without NEO4J_URI set, the tool should return stub data."""
        tools_mod = self._load_tools()
        env_backup = {k: os.environ.pop(k, None)
                      for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")}
        try:
            result = tools_mod.query_upstream_chain.invoke({"grade_id": "abs_3001mf2"})
            data = json.loads(result)
            assert data["source"] == "stub (Neo4j not configured)"
            assert isinstance(data["upstream_chain"], list)
            assert len(data["upstream_chain"]) > 0
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v

    def test_query_substitutes_returns_stub_when_no_env(self):
        tools_mod = self._load_tools()
        env_backup = {k: os.environ.pop(k, None)
                      for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")}
        try:
            result = tools_mod.query_substitutes.invoke({"grade_id": "abs_3001mf2"})
            data = json.loads(result)
            assert data["source"] == "stub (Neo4j not configured)"
            sub_ids = [s["substitute_id"] for s in data["substitutes"]]
            assert "ps_polymer" in sub_ids
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v

    def test_query_downstream_sectors_returns_stub_when_no_env(self):
        tools_mod = self._load_tools()
        env_backup = {k: os.environ.pop(k, None)
                      for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")}
        try:
            result = tools_mod.query_downstream_sectors.invoke({"grade_id": "abs_3001mf2"})
            data = json.loads(result)
            assert data["source"] == "stub (Neo4j not configured)"
            ds_ids = [d["downstream_id"] for d in data["downstream_sectors"]]
            assert "home_appliance" in ds_ids
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v
