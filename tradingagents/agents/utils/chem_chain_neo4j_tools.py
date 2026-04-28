"""LangChain tool wrappers for querying the industrial chain Neo4j graph.

These tools allow LLM agents (e.g. ChainPriceAnalyst) to retrieve
structural information about the supply chain directly from the graph
database instead of hard-coding product relationships.

The tools gracefully fall back to stub responses when Neo4j is unavailable
so that the rest of the forecast pipeline continues to work in development
environments without a running Neo4j instance.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_writer() -> Optional["ChainGraphNeo4jWriter"]:  # noqa: F821
    """Return a connected writer, or *None* if Neo4j is not configured."""
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    if not uri or not password:
        return None
    try:
        from tradingagents.chain_graph.neo4j_writer import ChainGraphNeo4jWriter
        return ChainGraphNeo4jWriter(uri=uri, user=user, password=password)
    except Exception as exc:
        logger.warning("Cannot connect to Neo4j: %s", exc)
        return None


def _stub_upstream(grade: str) -> str:
    """Return a hard-coded stub upstream chain for ABS grades."""
    data = {
        "grade": grade,
        "source": "stub (Neo4j not configured)",
        "upstream_chain": [
            {"source": "crude_oil", "source_name": "原油", "target": "naphtha", "target_name": "石脑油",
             "rel_type": "UPSTREAM_COST", "elasticity": 0.85},
            {"source": "naphtha", "source_name": "石脑油", "target": "styrene", "target_name": "苯乙烯",
             "rel_type": "UPSTREAM_COST", "elasticity": 0.75},
            {"source": "naphtha", "source_name": "石脑油", "target": "butadiene", "target_name": "丁二烯",
             "rel_type": "UPSTREAM_COST", "elasticity": 0.65},
            {"source": "styrene", "source_name": "苯乙烯", "target": "abs_polymer", "target_name": "ABS树脂",
             "rel_type": "UPSTREAM_COST", "elasticity": 0.55},
            {"source": "acrylonitrile", "source_name": "丙烯腈", "target": "abs_polymer", "target_name": "ABS树脂",
             "rel_type": "UPSTREAM_COST", "elasticity": 0.50},
            {"source": "butadiene", "source_name": "丁二烯", "target": "abs_polymer", "target_name": "ABS树脂",
             "rel_type": "UPSTREAM_COST", "elasticity": 0.45},
            {"source": "abs_polymer", "source_name": "ABS树脂", "target": grade.lower().replace("-", "_"),
             "target_name": grade, "rel_type": "SUPPLY_LINK", "elasticity": 0.90},
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def _stub_substitutes(grade: str) -> str:
    data = {
        "grade": grade,
        "source": "stub (Neo4j not configured)",
        "substitutes": [
            {"substitute_id": "ps_polymer", "substitute_name": "聚苯乙烯(PS)",
             "price_elasticity": 0.55, "confidence": 0.70,
             "conditions": ["价差超过800元/吨时切换概率增加"]},
            {"substitute_id": "san_polymer", "substitute_name": "SAN树脂",
             "price_elasticity": 0.50, "confidence": 0.65,
             "conditions": ["对透明度要求不高时"]},
            {"substitute_id": "pp_polymer", "substitute_name": "聚丙烯(PP)",
             "price_elasticity": 0.35, "confidence": 0.55,
             "conditions": ["对强度要求较低的包装类应用"]},
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def _stub_downstream(grade: str) -> str:
    data = {
        "grade": grade,
        "source": "stub (Neo4j not configured)",
        "downstream_sectors": [
            {"downstream_id": "home_appliance", "downstream_name": "家电行业",
             "demand_elasticity": 0.60, "confidence": 0.75,
             "conditions": ["家电旺季（3-5月，9-11月）需求拉动"]},
            {"downstream_id": "auto_parts", "downstream_name": "汽车配件",
             "demand_elasticity": 0.55, "confidence": 0.70,
             "conditions": ["汽车销售旺季"]},
            {"downstream_id": "electronics", "downstream_name": "电子电器",
             "demand_elasticity": 0.50, "confidence": 0.68,
             "conditions": ["消费电子备货周期"]},
            {"downstream_id": "packaging", "downstream_name": "包装材料",
             "demand_elasticity": 0.40, "confidence": 0.60,
             "conditions": ["价格敏感，易被PP替代"]},
        ],
    }
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# LangChain tools
# ---------------------------------------------------------------------------

@tool
def query_upstream_chain(grade_id: str) -> str:
    """Query the Neo4j industrial chain graph for the upstream supply chain of a product grade.

    Returns a JSON string describing every upstream node and relationship
    (feedstock → monomer → polymer → grade) including cost-transmission
    elasticity and typical price-lag ranges.  Shared upstream nodes (e.g.
    styrene used by multiple ABS grades) are returned only once – they are
    deduplicated in the graph database.

    When Neo4j is not configured (``NEO4J_URI`` / ``NEO4J_PASSWORD`` env vars
    not set), a built-in stub for common ABS grades is returned instead.

    Args:
        grade_id: Node ID of the target grade, e.g. ``"abs_3001mf2"`` or
                  ``"abs_0215a"``.  This corresponds to the ``id`` field in the
                  YAML chain definition.

    Returns:
        JSON string with keys ``grade``, ``source``, and ``upstream_chain``
        (list of relationship records).
    """
    writer = _get_writer()
    if writer is None:
        return _stub_upstream(grade_id)

    try:
        with writer:
            records = writer.get_upstream_chain(grade_id)
        return json.dumps(
            {"grade": grade_id, "source": "neo4j", "upstream_chain": records},
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        logger.warning("Neo4j query failed, falling back to stub: %s", exc)
        return _stub_upstream(grade_id)


@tool
def query_substitutes(grade_id: str) -> str:
    """Query the Neo4j graph for products that can substitute the given grade.

    Substitution relationships capture the competitive dynamics between ABS and
    alternative materials (PS, SAN, PP, etc.).  Each record includes a price
    elasticity coefficient and the market conditions under which switching is
    likely.

    Args:
        grade_id: Node ID of the target grade, e.g. ``"abs_3001mf2"``.

    Returns:
        JSON string with keys ``grade``, ``source``, and ``substitutes``
        (list of substitute records ordered by elasticity descending).
    """
    writer = _get_writer()
    if writer is None:
        return _stub_substitutes(grade_id)

    try:
        with writer:
            records = writer.get_substitutes(grade_id)
        return json.dumps(
            {"grade": grade_id, "source": "neo4j", "substitutes": records},
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        logger.warning("Neo4j query failed, falling back to stub: %s", exc)
        return _stub_substitutes(grade_id)


@tool
def query_downstream_sectors(grade_id: str) -> str:
    """Query the Neo4j graph for the downstream demand sectors of a grade.

    Returns every demand sector (home appliances, auto parts, electronics,
    packaging, …) linked to the specified grade together with demand elasticity
    and seasonal demand notes.

    Args:
        grade_id: Node ID of the target grade, e.g. ``"abs_3001mf2"``.

    Returns:
        JSON string with keys ``grade``, ``source``, and ``downstream_sectors``
        (list of downstream demand records ordered by elasticity descending).
    """
    writer = _get_writer()
    if writer is None:
        return _stub_downstream(grade_id)

    try:
        with writer:
            records = writer.get_downstream(grade_id)
        return json.dumps(
            {"grade": grade_id, "source": "neo4j", "downstream_sectors": records},
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        logger.warning("Neo4j query failed, falling back to stub: %s", exc)
        return _stub_downstream(grade_id)
