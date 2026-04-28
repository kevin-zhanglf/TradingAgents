"""Chemical plastics (化塑) price prediction entry point.

Usage:
    python chem_main.py

Or with custom parameters:
    python chem_main.py --grade ABS-3001MF2 --region 华北 --price-type deal --asof-date 2025-01-15
"""
import argparse
import json
import os
import sys
from datetime import datetime

from tradingagents.chem_schemas import render_final_forecast_md
from tradingagents.default_config import DEFAULT_CONFIG


def main():
    parser = argparse.ArgumentParser(description="Chemical plastics (化塑) price prediction system")
    parser.add_argument("--grade", default="ABS-3001MF2", help="Chemical grade code (e.g. ABS-3001MF2)")
    parser.add_argument("--region", default="华北", help="Target market region (e.g. 华北)")
    parser.add_argument("--price-type", default="deal", choices=["deal", "quote"], help="Price type")
    parser.add_argument("--asof-date", default=datetime.today().strftime("%Y-%m-%d"), help="Analysis date YYYY-MM-DD")
    parser.add_argument("--scenario", default="", help="Optional trader scenario text in Chinese")
    parser.add_argument("--analysts", default="chain_price,supply_demand,news_policy,demand_heat",
                        help="Comma-separated list of analysts to use")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--output-json", help="Path to write final forecast JSON")

    args = parser.parse_args()

    selected_analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]

    print(f"\n{'='*60}")
    print(f"化塑价格预测系统 (Chemical Plastics Price Prediction)")
    print(f"{'='*60}")
    print(f"品种: {args.grade}")
    print(f"地区: {args.region}")
    print(f"价格类型: {args.price_type}")
    print(f"分析基准日: {args.asof_date}")
    print(f"启用分析师: {selected_analysts}")
    if args.scenario:
        print(f"情景输入: {args.scenario}")
    print(f"{'='*60}\n")

    # Build config (uses defaults; production would override llm settings here)
    config = DEFAULT_CONFIG.copy()

    from tradingagents.graph.chem_graph import ChemForecastGraph

    graph = ChemForecastGraph(
        selected_analysts=selected_analysts,
        debug=args.debug,
        config=config,
    )

    print("正在运行预测图... (Running forecast graph...)\n")
    final_state, final_forecast = graph.propagate(
        grade=args.grade,
        region=args.region,
        price_type=args.price_type,
        asof_date=args.asof_date,
        scenario_input=args.scenario,
    )

    print("\n" + "="*60)
    print("预测结果 (Forecast Results)")
    print("="*60)
    md_report = render_final_forecast_md(final_forecast)
    print(md_report)

    if args.output_json:
        output_path = args.output_json
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_forecast.model_dump_json(indent=2))
        print(f"\n预测JSON已保存至: {output_path}")

    return final_forecast


if __name__ == "__main__":
    main()
