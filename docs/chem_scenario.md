# Chemical Plastics (化塑) Price Prediction System — Scenario Guide

## Overview

The chemical plastics forecasting system extends TradingAgents with a multi-agent pipeline designed for ABS (Acrylonitrile-Butadiene-Styrene) resin price prediction in the Chinese market.

## Architecture

```
START
  ↓
Chain Price Analyst  →  tools_chain_price (loop)  →  Msg Clear Chain Price
  ↓
Supply Demand Analyst  →  tools_supply_demand (loop)  →  Msg Clear Supply Demand
  ↓
News Policy Analyst  →  tools_news_policy (loop)  →  Msg Clear News Policy
  ↓
Demand Heat Analyst  →  tools_demand_heat (loop)  →  Msg Clear Demand Heat
  ↓
Model Agent  (pure-computation P10/P50/P90 baseline)
  ↓
Scenario Agent  (LLM extracts ScenarioSpec from reports)
  ↓
Forecast Synthesizer  (applies OverlayEngine + narrative)
  ↓
END
```

## Analyst Roles

| Analyst | Tools | Output |
|---------|-------|--------|
| Chain Price | `get_chem_price_series`, `get_upstream_price_series` | Price trend + upstream cost analysis |
| Supply Demand | `get_inventory`, `get_operating_rate`, `get_import_export` | Inventory / operating rate / trade flow |
| News Policy | `search_chem_news`, `search_policy_news` | Market events + policy impacts |
| Demand Heat | `get_quote_activity`, `get_deal_activity` | Quote/deal activity, buyer heat |

## Scenario Specification

The `ScenarioSpec` captures structured market assumptions:

```python
class ScenarioSpec(BaseModel):
    trader_bias: Literal["bullish", "neutral", "bearish"]
    inventory_signal: Literal["high", "normal", "low"]
    supply_disruption: bool
    demand_heat: Literal["strong", "normal", "weak"]
    max_p50_shift_pct: float  # Hard cap, default ±5%
```

## Overlay Engine Rules

The `OverlayEngine` applies deterministic adjustments to the P50 baseline:

| Signal | Adjustment |
|--------|------------|
| `trader_bias=bullish` | +1.5% |
| `trader_bias=bearish` | -1.5% |
| `inventory_signal=high` | -1.5% |
| `inventory_signal=low` | +1.5% |
| `supply_disruption=True` | +2.0% |
| `demand_heat=strong` | +1.0% |
| `demand_heat=weak` | -1.0% |
| Hard cap | ±`max_p50_shift_pct` (default ±5%) |

When `supply_disruption=True` or `|shift| > 2%`, the P10/P90 interval is widened by 30%.

## Usage Examples

### Basic run
```bash
python chem_main.py
```

### Custom grade and date
```bash
python chem_main.py --grade ABS-3001MF2 --region 华北 --price-type deal --asof-date 2025-03-01
```

### With trader scenario input
```bash
python chem_main.py \
  --grade ABS-3001MF2 \
  --region 华北 \
  --scenario "近期吉化检修，库存偏低，家电旺季备货，预计价格偏多" \
  --asof-date 2025-03-01
```

### Subset analysts
```bash
python chem_main.py --analysts chain_price,news_policy
```

### Save JSON output
```bash
python chem_main.py --output-json forecast_output.json
```

## Supply Chain Graph (abs_chain.yaml)

The `tradingagents/chain_graph/abs_chain.yaml` defines the ABS supply chain:

- **Feedstocks**: 原油 → 石脑油 → 苯乙烯/丁二烯; 煤炭/天然气 → 丙烯腈
- **Monomers**: 苯乙烯 (55%), 丁二烯 (25%), 丙烯腈 (20%)
- **Polymers**: ABS树脂, PS, SAN, PP (substitutes)
- **Grades**: ABS-3001MF2 (吉化), ABS-0215A (台化)
- **Downstream**: 家电, 汽车配件, 电子电器, 包装
- **Regions**: 华北, 华东, 华南

Use `load_graph()` and `get_subgraph()` from `tradingagents.chain_graph` to programmatically access the chain structure.

## Data Sources (Stub Implementation)

| Data Type | Real Source | Stub |
|-----------|-------------|------|
| Spot prices | 卓创资讯 (SCI) | Random walk from base price |
| Inventory | 百川盈孚 | Weekly random walk |
| Operating rate | 卓创资讯 | Weekly bounded random walk |
| Import/Export | 中国海关 | Monthly random walk |
| News | 卓创资讯, 隆众资讯 | Template-based stubs |
| Policy | wind政策数据库 | Template-based stubs |
| Quote activity | 化纤网 | Simulated bid-ask data |
| Deal activity | 找塑料网 | Simulated deal data |

## Output Schema

```python
class FinalForecast(BaseModel):
    base_forecast: BaseForecast        # Statistical baseline
    scenario_spec: Optional[ScenarioSpec]  # Scenario assumptions
    overlay_explain: Optional[OverlayExplain]  # Adjustment details
    forecast: List[PriceForecastPoint]  # 30-day P10/P50/P90

class PriceForecastPoint(BaseModel):
    date: str   # YYYY-MM-DD
    p10: float  # Pessimistic price (元/吨)
    p50: float  # Central price (元/吨)
    p90: float  # Optimistic price (元/吨)
```
