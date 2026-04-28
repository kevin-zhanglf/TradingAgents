"""Model agent: pure-computation baseline P10/P50/P90 forecast for ABS prices."""
import json
import math
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage
from tradingagents.agents.utils.chem_price_tools import get_chem_price_series
from tradingagents.chem_schemas import BaseForecast, PriceForecastPoint


def create_model_agent(llm):
    """Create a model agent that computes baseline P10/P50/P90 forecast.

    This agent does NOT use LLM for tool calling. It directly invokes the price
    tool functions and computes statistics to build a BaseForecast.
    """

    def model_agent_node(state):
        grade = state.get("grade_of_interest", "ABS-3001MF2")
        region = state.get("region", "华北")
        price_type = state.get("price_type", "deal")
        asof_date = state.get("asof_date", "2025-01-15")

        end_dt = datetime.strptime(asof_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=90)
        start_str = start_dt.strftime("%Y-%m-%d")

        raw_json = get_chem_price_series.invoke({
            "grade": grade,
            "region": region,
            "price_type": price_type,
            "start_date": start_str,
            "end_date": asof_date,
        })
        price_data = json.loads(raw_json)
        prices = [d["price"] for d in price_data["data"]]

        if not prices:
            prices = [13500.0]

        window = min(30, len(prices))
        recent_prices = prices[-window:]
        n = len(recent_prices)
        mean_price = sum(recent_prices) / n
        variance = sum((p - mean_price) ** 2 for p in recent_prices) / max(n - 1, 1)
        std_price = math.sqrt(variance)

        if len(prices) >= 14:
            last7 = sum(prices[-7:]) / 7
            prev7 = sum(prices[-14:-7]) / 7
            daily_drift = (last7 - prev7) / 7.0
        else:
            daily_drift = 0.0

        # 0.5% daily drift cap prevents unrealistic extrapolation over 30-day horizon
        MAX_DAILY_DRIFT_RATIO = 0.005
        max_daily_drift = mean_price * MAX_DAILY_DRIFT_RATIO
        daily_drift = max(min(daily_drift, max_daily_drift), -max_daily_drift)

        # Z-score for 80% prediction interval (±1.28σ covers ~80% of distribution)
        Z_SCORE_80PCT_INTERVAL = 1.28
        half_interval = Z_SCORE_80PCT_INTERVAL * std_price

        forecast_points = []
        for day in range(1, 31):
            forecast_dt = end_dt + timedelta(days=day)
            p50 = mean_price + daily_drift * day
            forecast_points.append(PriceForecastPoint(
                date=forecast_dt.strftime("%Y-%m-%d"),
                p10=round(p50 - half_interval, 2),
                p50=round(p50, 2),
                p90=round(p50 + half_interval, 2),
            ))

        key_drivers = []
        if state.get("chain_price_report"):
            key_drivers.append("上游单体（苯乙烯/丁二烯/丙烯腈）成本传导")
        if state.get("supply_demand_report"):
            key_drivers.append("库存水平与开工率变化")
        if state.get("news_policy_report"):
            key_drivers.append("行业资讯与政策动态")
        if state.get("demand_heat_report"):
            key_drivers.append("下游需求热度（成交活跃度）")
        if not key_drivers:
            key_drivers = ["历史价格统计规律", "上游成本压力"]

        confidence_note = (
            f"基于过去{window}个交易日历史价格的滚动均值±{Z_SCORE_80PCT_INTERVAL}σ区间，"
            f"均价={mean_price:.0f}，标准差={std_price:.0f}，日均漂移={daily_drift:+.1f}元/吨。"
            f"此为统计基线，未包含专项调研信息。"
        )

        base_forecast = BaseForecast(
            grade=grade,
            region=region,
            price_type=price_type,
            asof_date=asof_date,
            horizon_days=30,
            forecast=forecast_points,
            key_drivers=key_drivers,
            model_name="rolling_stat_baseline_v1",
            confidence_note=confidence_note,
        )

        base_forecast_json = base_forecast.model_dump_json(indent=2)
        msg = HumanMessage(
            content=f"模型Agent已计算完成基础预测。P50均值约{mean_price:.0f}元/吨，30日预测区间宽度约{half_interval*2:.0f}元/吨。"
        )

        return {"messages": [msg], "base_forecast_json": base_forecast_json}

    return model_agent_node
