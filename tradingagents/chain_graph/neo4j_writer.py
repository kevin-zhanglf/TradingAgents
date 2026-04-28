"""Neo4j writer for industrial chain graph data.

Writes ChainGraph nodes and edges to Neo4j using MERGE statements so that
shared upstream / downstream nodes (e.g. styrene, butadiene) are never
duplicated across different product grades.  The resulting graph forms a
proper directed tree structure:

    feedstock → monomer → polymer → grade
                                       ├── [:DOWNSTREAM]  → downstream sector
                                       └── [:SUBSTITUTE]  → substitute product

Substitute relationships are stored as a dedicated ``[:SUBSTITUTE]``
relationship type so they can be queried independently from cost / supply links.

Usage
-----
>>> from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter
>>> from tradingagents.chain_graph import load_graph
>>> import os
>>>
>>> chain = load_graph("tradingagents/chain_graph/abs_chain.yaml")
>>> writer = ChainGraphNeo4jWriter(
...     uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
...     user=os.getenv("NEO4J_USER", "neo4j"),
...     password=os.getenv("NEO4J_PASSWORD", "password"),
... )
>>> with writer:
...     writer.write_graph(chain, clear=False)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .schema import ChainGraph, ChainNode, ChainEdge, EdgeType, NodeType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional neo4j import – makes the module importable without the package
# ---------------------------------------------------------------------------
try:
    from neo4j import GraphDatabase  # type: ignore
    _HAS_NEO4J = True
except ImportError:
    GraphDatabase = None  # type: ignore
    _HAS_NEO4J = False

# ---------------------------------------------------------------------------
# Relationship type mapping
# EdgeType enum value → Neo4j relationship type label
# ---------------------------------------------------------------------------
_REL_TYPE: Dict[str, str] = {
    EdgeType.UPSTREAM_COST: "UPSTREAM_COST",
    EdgeType.SUBSTITUTE: "SUBSTITUTE",
    EdgeType.SUPPLY_LINK: "SUPPLY_LINK",
    EdgeType.DEMAND_LINK: "DEMAND_LINK",
    EdgeType.REGIONAL_ARBITRAGE: "REGIONAL_ARBITRAGE",
}

# Neo4j node label per NodeType
_NODE_LABEL: Dict[str, str] = {
    NodeType.FEEDSTOCK: "Feedstock",
    NodeType.MONOMER: "Monomer",
    NodeType.POLYMER: "Polymer",
    NodeType.GRADE: "Grade",
    NodeType.SUBSTITUTE: "Substitute",
    NodeType.DOWNSTREAM: "Downstream",
    NodeType.REGION: "Region",
}


class ChainGraphNeo4jWriter:
    """Writes a :class:`~tradingagents.chain_graph.schema.ChainGraph` to Neo4j.

    All write operations use ``MERGE`` on the ``id`` property so that nodes and
    relationships are idempotent – calling :meth:`write_graph` multiple times
    (or for multiple grades that share the same upstream nodes) will never
    create duplicate entries.

    Parameters
    ----------
    uri:
        Bolt / bolt+s / neo4j URI, e.g. ``bolt://localhost:7687``.
    user:
        Neo4j username (default ``"neo4j"``).
    password:
        Neo4j password.
    database:
        Target database name (default ``"neo4j"``).
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ) -> None:
        if not _HAS_NEO4J:
            raise ImportError(
                "The 'neo4j' package is required. Install it with: pip install neo4j>=5.0"
            )

        try:
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
        except Exception as exc:
            raise ConnectionError(
                f"Failed to create Neo4j driver for URI '{uri}'. "
                "Check that NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD are correct "
                f"and that the Neo4j server is reachable. Original error: {exc}"
            ) from exc
        self._database = database

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "ChainGraphNeo4jWriter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying Neo4j driver connection."""
        self._driver.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_graph(self, graph: ChainGraph, *, clear: bool = False) -> None:
        """Write all nodes and edges of *graph* to Neo4j.

        Parameters
        ----------
        graph:
            The full :class:`ChainGraph` to persist.
        clear:
            When ``True``, delete **all** existing chain-graph nodes before
            writing.  Use with caution in production.
        """
        with self._driver.session(database=self._database) as session:
            if clear:
                session.execute_write(self._clear_graph)

            session.execute_write(self._ensure_constraints)

            for node in graph.nodes:
                session.execute_write(self._merge_node, node)
                logger.debug("Merged node: %s (%s)", node.id, node.node_type)

            for edge in graph.edges:
                session.execute_write(self._merge_edge, edge)
                logger.debug("Merged edge: %s -[%s]-> %s", edge.source, edge.edge_type, edge.target)

        logger.info(
            "Wrote %d nodes and %d edges to Neo4j database '%s'",
            len(graph.nodes),
            len(graph.edges),
            self._database,
        )

    def write_grade_subgraph(
        self,
        graph: ChainGraph,
        grade_id: str,
        hops: int = 3,
        *,
        clear: bool = False,
    ) -> None:
        """Write only the k-hop neighbourhood of a specific grade to Neo4j.

        This is a convenience wrapper that calls :func:`~tradingagents.chain_graph.loader.get_subgraph`
        and then :meth:`write_graph`.

        Parameters
        ----------
        graph:
            The full :class:`ChainGraph` to source data from.
        grade_id:
            Node ``id`` of the target grade (e.g. ``"abs_3001mf2"``).
        hops:
            Number of graph hops to include around the grade node.
        clear:
            When ``True``, clear the graph before writing.
        """
        from .loader import get_subgraph  # local import to avoid circular deps

        subgraph = get_subgraph(graph, grade_id, target_region="", hops=hops)
        self.write_graph(subgraph, clear=clear)

    def get_upstream_chain(self, grade_id: str) -> List[Dict[str, Any]]:
        """Return the upstream supply chain for a grade as a list of records.

        Each record contains ``source``, ``target``, ``rel_type``,
        ``elasticity``, and ``lag_days``.
        """
        cypher = """
            MATCH path = (g {id: $grade_id})<-[:UPSTREAM_COST|SUPPLY_LINK*1..5]-(upstream)
            UNWIND relationships(path) AS rel
            RETURN
                startNode(rel).id AS source,
                startNode(rel).name AS source_name,
                endNode(rel).id AS target,
                endNode(rel).name AS target_name,
                type(rel) AS rel_type,
                rel.elasticity AS elasticity,
                rel.lag_min_days AS lag_min_days,
                rel.lag_max_days AS lag_max_days
            ORDER BY source
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, grade_id=grade_id)
            return [dict(r) for r in result]

    def get_substitutes(self, grade_id: str) -> List[Dict[str, Any]]:
        """Return all substitute products for a grade."""
        cypher = """
            MATCH (g {id: $grade_id})-[r:SUBSTITUTE]->(sub)
            RETURN
                g.id AS grade_id,
                g.name AS grade_name,
                sub.id AS substitute_id,
                sub.name AS substitute_name,
                r.elasticity AS price_elasticity,
                r.confidence AS confidence,
                r.conditions AS conditions
            ORDER BY r.elasticity DESC
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, grade_id=grade_id)
            return [dict(r) for r in result]

    def get_downstream(self, grade_id: str) -> List[Dict[str, Any]]:
        """Return all downstream demand sectors for a grade."""
        cypher = """
            MATCH (g {id: $grade_id})-[r:DEMAND_LINK]->(ds)
            RETURN
                g.id AS grade_id,
                ds.id AS downstream_id,
                ds.name AS downstream_name,
                r.elasticity AS demand_elasticity,
                r.confidence AS confidence,
                r.conditions AS conditions
            ORDER BY r.elasticity DESC
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, grade_id=grade_id)
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Internal helpers (called inside session.execute_write)
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_graph(tx: Any) -> None:
        """Delete all ChainNode nodes (and their relationships)."""
        tx.run(
            "MATCH (n:ChainNode) DETACH DELETE n"
        )

    @staticmethod
    def _ensure_constraints(tx: Any) -> None:
        """Create uniqueness constraints if they do not already exist."""
        try:
            tx.run(
                "CREATE CONSTRAINT chain_node_id IF NOT EXISTS "
                "FOR (n:ChainNode) REQUIRE n.id IS UNIQUE"
            )
        except Exception:
            # Some older Neo4j versions use different syntax; ignore and continue.
            logger.debug("Could not create uniqueness constraint (may already exist).", exc_info=True)

    @staticmethod
    def _merge_node(tx: Any, node: ChainNode) -> None:
        """MERGE a single ChainNode into Neo4j."""
        node_label = _NODE_LABEL.get(node.node_type, "ChainNode")

        # Serialise price series as a JSON string for storage
        series_json = json.dumps(
            [s.model_dump() for s in node.series], ensure_ascii=False
        )

        cypher = (
            f"MERGE (n:ChainNode:{node_label} {{id: $id}}) "
            "SET n.name = $name, "
            "    n.node_type = $node_type, "
            "    n.description = $description, "
            "    n.region = $region, "
            "    n.series_json = $series_json"
        )
        tx.run(
            cypher,
            id=node.id,
            name=node.name,
            node_type=node.node_type.value,
            description=node.description,
            region=node.region or "",
            series_json=series_json,
        )

    @staticmethod
    def _merge_edge(tx: Any, edge: ChainEdge) -> None:
        """MERGE a single ChainEdge into Neo4j."""
        rel_type = _REL_TYPE.get(edge.edge_type, "RELATED_TO")

        cypher = (
            "MATCH (src:ChainNode {id: $source}), (tgt:ChainNode {id: $target}) "
            f"MERGE (src)-[r:{rel_type}]->(tgt) "
            "SET r.edge_type = $edge_type, "
            "    r.lag_min_days = $lag_min, "
            "    r.lag_max_days = $lag_max, "
            "    r.elasticity = $elasticity, "
            "    r.confidence = $confidence, "
            "    r.conditions = $conditions"
        )
        tx.run(
            cypher,
            source=edge.source,
            target=edge.target,
            edge_type=edge.edge_type.value,
            lag_min=edge.lag_days[0],
            lag_max=edge.lag_days[1],
            elasticity=edge.elasticity,
            confidence=edge.confidence,
            conditions=edge.conditions,
        )
