"""Deterministic scenario overlay engine for chemical plastics price forecasting."""
from __future__ import annotations
from typing import List
from .chem_schemas import BaseForecast, ScenarioSpec, FinalForecast, PriceForecastPoint, OverlayExplain


class OverlayEngine:
    """Applies ScenarioSpec to BaseForecast to produce FinalForecast.

    Rules (all capped at ±max_p50_shift_pct, default ±5%):
    - trader_bias=bullish: +1.5% base bias
    - trader_bias=bearish: -1.5% base bias
    - inventory_signal=high: -1.5% pressure
    - inventory_signal=low: +1.5% pressure
    - supply_disruption=True: +2.0% bullish shock
    - demand_heat=strong: +1.0%; weak: -1.0%
    - P10/P90 interval widened when supply_disruption=True or |total_shift| > 2%
    """

    def apply(self, base: BaseForecast, scenario: ScenarioSpec) -> FinalForecast:
        assumptions: List[str] = []
        risk_notes: List[str] = []

        shift_pct = 0.0

        if scenario.trader_bias == "bullish":
            shift_pct += 1.5
            assumptions.append("交易员偏多，预计价格上行（+1.5%）")
        elif scenario.trader_bias == "bearish":
            shift_pct -= 1.5
            assumptions.append("交易员偏空，预计价格承压（-1.5%）")
        else:
            assumptions.append("交易员中性，基础预测不调整方向")

        if scenario.inventory_signal == "high":
            shift_pct -= 1.5
            assumptions.append("库存偏高，供应压力拖累价格（-1.5%）")
            risk_notes.append("如库存去化加速，实际跌幅可能收窄")
        elif scenario.inventory_signal == "low":
            shift_pct += 1.5
            assumptions.append("库存偏低，供应偏紧支撑价格（+1.5%）")
            risk_notes.append("如进口补货及时，涨幅可能不及预期")
        else:
            assumptions.append("库存正常，库存因素中性")

        if scenario.supply_disruption:
            shift_pct += 2.0
            assumptions.append("存在供应扰动事件，短期价格有额外支撑（+2.0%）")
            risk_notes.append("供应扰动持续时间不确定，需持续跟踪")

        if scenario.demand_heat == "strong":
            shift_pct += 1.0
            assumptions.append("下游需求旺盛，拉动价格上行（+1.0%）")
        elif scenario.demand_heat == "weak":
            shift_pct -= 1.0
            assumptions.append("下游需求疲弱，抑制价格上行（-1.0%）")
        else:
            assumptions.append("下游需求正常，需求因素中性")

        max_shift_cap = scenario.max_p50_shift_pct
        original_shift = shift_pct
        shift_pct = max(min(shift_pct, max_shift_cap), -max_shift_cap)
        if abs(original_shift) > max_shift_cap:
            risk_notes.append(f"综合调整幅度已触及±{max_shift_cap}%上限（原始计算：{original_shift:+.1f}%）")

        interval_widened = scenario.supply_disruption or abs(shift_pct) > 2.0
        if interval_widened:
            risk_notes.append("不确定性较高，P10/P90置信区间已适当扩宽")

        multiplier = 1.0 + shift_pct / 100.0
        # 1.3 = 30% interval widening applied under high-uncertainty conditions
        # (supply disruption or absolute shift exceeding 2% threshold)
        widen_factor = 1.3 if interval_widened else 1.0

        final_points: List[PriceForecastPoint] = []
        for pt in base.forecast:
            new_p50 = pt.p50 * multiplier
            orig_half = (pt.p90 - pt.p10) / 2.0
            new_half = orig_half * widen_factor
            final_points.append(PriceForecastPoint(
                date=pt.date,
                p10=round(new_p50 - new_half, 2),
                p50=round(new_p50, 2),
                p90=round(new_p50 + new_half, 2),
            ))

        base_p50_avg = sum(pt.p50 for pt in base.forecast) / max(len(base.forecast), 1)
        final_p50_avg = sum(pt.p50 for pt in final_points) / max(len(final_points), 1)

        overlay_explain = OverlayExplain(
            direction_triggered=(shift_pct != 0.0),
            base_p50_30d_avg=round(base_p50_avg, 2),
            final_p50_30d_avg=round(final_p50_avg, 2),
            p50_shift_pct=round(shift_pct, 4),
            interval_widened=interval_widened,
            key_assumptions=assumptions,
            risk_notes=risk_notes,
        )

        return FinalForecast(
            base_forecast=base,
            scenario_spec=scenario,
            overlay_explain=overlay_explain,
            forecast=final_points,
        )
