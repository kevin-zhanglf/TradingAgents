"""Pydantic schemas for chemical plastics price forecasting system."""
from __future__ import annotations
from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class PriceForecastPoint(BaseModel):
    date: str = Field(..., description="Forecast date YYYY-MM-DD")
    p10: float = Field(..., description="P10 (pessimistic) price in 元/吨")
    p50: float = Field(..., description="P50 (central/median) price in 元/吨")
    p90: float = Field(..., description="P90 (optimistic) price in 元/吨")


class BaseForecast(BaseModel):
    grade: str = Field(..., description="Chemical grade code e.g. ABS-3001MF2")
    region: str = Field(..., description="Target market region e.g. 华北")
    price_type: str = Field(..., description="Price type: quote or deal")
    asof_date: str = Field(..., description="Analysis as-of date YYYY-MM-DD")
    horizon_days: int = Field(30, description="Forecast horizon in days")
    forecast: List[PriceForecastPoint] = Field(..., description="Daily P10/P50/P90 forecast")
    key_drivers: List[str] = Field(default_factory=list, description="Top price drivers identified")
    model_name: str = Field("rolling_stat_baseline", description="Model name used")
    confidence_note: str = Field("", description="Model confidence caveat")


class ScenarioSpec(BaseModel):
    scenario_id: str = Field(..., description="Unique scenario identifier")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    trader_bias: Literal["bullish", "neutral", "bearish"] = Field(..., description="Trader directional bias")
    trader_rationale: str = Field("", description="Trader reasoning for the bias")
    inventory_survey_text: str = Field("", description="Raw inventory survey text")
    inventory_signal: Literal["high", "normal", "low"] = Field("normal", description="Inventory level signal")
    supply_disruption: bool = Field(False, description="Whether there is a supply disruption")
    demand_heat: Literal["strong", "normal", "weak"] = Field("normal", description="Downstream demand heat")
    max_p50_shift_pct: float = Field(5.0, description="Hard cap on P50 shift percentage")


class OverlayExplain(BaseModel):
    direction_triggered: bool = Field(..., description="Whether a direction signal was triggered")
    base_p50_30d_avg: float = Field(..., description="Base forecast average P50 over horizon")
    final_p50_30d_avg: float = Field(..., description="Final adjusted average P50 over horizon")
    p50_shift_pct: float = Field(..., description="Total P50 shift applied in percent")
    interval_widened: bool = Field(..., description="Whether P10/P90 interval was widened")
    key_assumptions: List[str] = Field(default_factory=list)
    risk_notes: List[str] = Field(default_factory=list)


class FinalForecast(BaseModel):
    base_forecast: BaseForecast
    scenario_spec: Optional[ScenarioSpec] = None
    overlay_explain: Optional[OverlayExplain] = None
    forecast: List[PriceForecastPoint] = Field(..., description="Final adjusted daily forecast")


# ── Markdown rendering helpers ──────────────────────────────────────────────

def render_forecast_table(forecast: List[PriceForecastPoint], title: str = "价格预测区间") -> str:
    lines = [f"## {title}", "", "| 日期 | P10 (悲观) | P50 (中性) | P90 (乐观) |", "| --- | --- | --- | --- |"]
    for p in forecast:
        lines.append(f"| {p.date} | {p.p10:.0f} | {p.p50:.0f} | {p.p90:.0f} |")
    return "\n".join(lines)


def render_overlay_explain(oe: OverlayExplain) -> str:
    lines = [
        "## 情景叠加说明",
        f"- 方向信号触发: {'是' if oe.direction_triggered else '否'}",
        f"- 基础P50均值: {oe.base_p50_30d_avg:.0f} 元/吨",
        f"- 最终P50均值: {oe.final_p50_30d_avg:.0f} 元/吨",
        f"- P50调整幅度: {oe.p50_shift_pct:+.2f}%",
        f"- 置信区间扩宽: {'是' if oe.interval_widened else '否'}",
        "",
        "**关键假设:**",
    ]
    for a in oe.key_assumptions:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("**风险提示:**")
    for r in oe.risk_notes:
        lines.append(f"- {r}")
    return "\n".join(lines)


def render_final_forecast_md(ff: FinalForecast) -> str:
    parts = [
        f"# {ff.base_forecast.grade} {ff.base_forecast.region} 价格预测报告",
        f"**预测基准日:** {ff.base_forecast.asof_date}  |  **价格类型:** {ff.base_forecast.price_type}  |  **预测期:** {ff.base_forecast.horizon_days}天",
        "",
    ]
    if ff.scenario_spec:
        parts += [
            "## 情景假设",
            f"- 交易员偏向: {ff.scenario_spec.trader_bias}",
            f"- 库存信号: {ff.scenario_spec.inventory_signal}",
            f"- 供应扰动: {'有' if ff.scenario_spec.supply_disruption else '无'}",
            f"- 需求热度: {ff.scenario_spec.demand_heat}",
            f"- 交易员判断: {ff.scenario_spec.trader_rationale}",
            "",
        ]
    if ff.overlay_explain:
        parts.append(render_overlay_explain(ff.overlay_explain))
        parts.append("")
    parts.append(render_forecast_table(ff.forecast))
    if ff.base_forecast.key_drivers:
        parts += ["", "## 关键驱动因素", ""]
        for d in ff.base_forecast.key_drivers:
            parts.append(f"- {d}")
    return "\n".join(parts)
