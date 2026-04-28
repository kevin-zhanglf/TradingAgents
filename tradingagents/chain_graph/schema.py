from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    FEEDSTOCK = "feedstock"
    MONOMER = "monomer"
    POLYMER = "polymer"
    GRADE = "grade"
    SUBSTITUTE = "substitute"
    DOWNSTREAM = "downstream"
    REGION = "region"


class EdgeType(str, Enum):
    UPSTREAM_COST = "upstream_cost"
    SUBSTITUTE = "substitute"
    SUPPLY_LINK = "supply_link"
    DEMAND_LINK = "demand_link"
    REGIONAL_ARBITRAGE = "regional_arbitrage"


class PriceSeriesRef(BaseModel):
    series_id: str
    price_type: str  # "quote" or "deal"
    region: str
    freq: str = "D"
    unit: str = "元/吨"
    tax_included: bool = True
    source: str = "卓创资讯"


class ChainNode(BaseModel):
    id: str
    name: str
    node_type: NodeType
    series: List[PriceSeriesRef] = Field(default_factory=list)
    region: Optional[str] = None
    description: str = ""


class ChainEdge(BaseModel):
    source: str
    target: str
    edge_type: EdgeType
    lag_days: Tuple[int, int] = (0, 7)
    elasticity: float = 0.5
    confidence: float = 0.7
    conditions: List[str] = Field(default_factory=list)


class ChainGraph(BaseModel):
    nodes: List[ChainNode]
    edges: List[ChainEdge]
