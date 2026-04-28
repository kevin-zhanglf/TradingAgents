"""Forecast synthesizer: combines base forecast with scenario overlay to produce final forecast."""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from tradingagents.chem_schemas import BaseForecast, ScenarioSpec, FinalForecast, render_final_forecast_md
from tradingagents.chem_overlay import OverlayEngine


def create_forecast_synthesizer(llm):
    """Create a forecast synthesizer node."""

    def forecast_synthesizer_node(state):
        base_forecast_json = state.get("base_forecast_json", "")
        scenario_spec_json = state.get("scenario_spec_json", "")

        if not base_forecast_json:
            msg = HumanMessage(content="错误：未找到基础预测数据，无法生成最终预测。")
            return {"messages": [msg], "final_forecast_json": ""}

        base_forecast = BaseForecast.model_validate_json(base_forecast_json)

        if scenario_spec_json:
            scenario = ScenarioSpec.model_validate_json(scenario_spec_json)
            engine = OverlayEngine()
            final_forecast = engine.apply(base_forecast, scenario)
        else:
            final_forecast = FinalForecast(
                base_forecast=base_forecast,
                scenario_spec=None,
                overlay_explain=None,
                forecast=base_forecast.forecast,
            )

        forecast_summary = render_final_forecast_md(final_forecast)

        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一位资深ABS市场研究员，负责撰写价格预测报告摘要。
请根据以下预测数据，用中文撰写一段简洁的分析摘要（200-400字），包含：
1. 预测期内价格的总体方向（上行/下行/震荡）
2. 关键支撑/压力位
3. 主要驱动因素
4. 主要风险提示
只输出摘要文字，不要输出markdown格式。"""),
            ("human", "{forecast_summary}"),
        ])
        prompt = prompt.partial(forecast_summary=forecast_summary[:3000])

        chain = prompt | llm
        narrative_result = chain.invoke({})
        narrative = narrative_result.content if hasattr(narrative_result, "content") else str(narrative_result)

        final_forecast_json = final_forecast.model_dump_json(indent=2)

        msg = HumanMessage(
            content=f"预测合成完成。\n\n{narrative}\n\n{forecast_summary}"
        )

        return {"messages": [msg], "final_forecast_json": final_forecast_json}

    return forecast_synthesizer_node
