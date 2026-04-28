"""Scenario agent: extracts ScenarioSpec from analyst reports using LLM."""
import json
import uuid
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from tradingagents.chem_schemas import ScenarioSpec


def create_scenario_agent(llm):
    """Create a scenario agent that extracts structured ScenarioSpec from analyst reports."""

    def scenario_agent_node(state):
        asof_date = state.get("asof_date", "2025-01-15")
        scenario_input = state.get("scenario_input", "")
        chain_price_report = state.get("chain_price_report", "")
        supply_demand_report = state.get("supply_demand_report", "")
        news_policy_report = state.get("news_policy_report", "")
        demand_heat_report = state.get("demand_heat_report", "")

        # Note: the JSON example below must escape braces so ChatPromptTemplate
        # doesn't interpret them as template placeholders. Use doubled braces.
        system_prompt = """你是一位资深ABS市场情景分析师。你的任务是综合所有分析报告，提炼出结构化的市场情景参数。

你的任务是输出一个严格的JSON对象（不要有任何其他文字），包含以下字段：
{{
  "trader_bias": "bullish" | "neutral" | "bearish",
  "trader_rationale": "简要说明偏向判断依据（中文，不超过200字）",
  "inventory_survey_text": "库存情况摘要（中文）",
  "inventory_signal": "high" | "normal" | "low",
  "supply_disruption": true | false,
  "demand_heat": "strong" | "normal" | "weak"
}}

判断规则：
- trader_bias: 综合所有报告的价格方向信号，多个利多信号→bullish，多个利空→bearish，混合→neutral
- inventory_signal: 根据supply_demand_report，库存天数>60天→high，<30天→low，其余→normal
- supply_disruption: news_policy_report中有装置停产/检修/贸易中断等明确事件→true，否则false
- demand_heat: demand_heat_report中成交活跃度评级→strong/normal/weak"""

        user_content = f"""请综合以下报告提炼情景参数：

**交易员原始情景输入:**
{scenario_input if scenario_input else "（无）"}

**产业链价格报告:**
{chain_price_report[:1000] if chain_price_report else "（未提供）"}

**供需基本面报告:**
{supply_demand_report[:1000] if supply_demand_report else "（未提供）"}

**资讯与政策报告:**
{news_policy_report[:1000] if news_policy_report else "（未提供）"}

**需求热度报告:**
{demand_heat_report[:1000] if demand_heat_report else "（未提供）"}

请输出JSON："""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{user_content}"),
        ])
        prompt = prompt.partial(user_content=user_content)

        chain = prompt | llm
        result = chain.invoke({})

        content = result.content if hasattr(result, "content") else str(result)

        scenario_dict = {}
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                scenario_dict = json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        scenario = ScenarioSpec(
            scenario_id=str(uuid.uuid4()),
            created_at=datetime.now().isoformat(),
            trader_bias=scenario_dict.get("trader_bias", "neutral"),
            trader_rationale=scenario_dict.get("trader_rationale", "基于综合分析，市场方向中性"),
            inventory_survey_text=scenario_dict.get("inventory_survey_text", "库存数据参见供需报告"),
            inventory_signal=scenario_dict.get("inventory_signal", "normal"),
            supply_disruption=bool(scenario_dict.get("supply_disruption", False)),
            demand_heat=scenario_dict.get("demand_heat", "normal"),
        )

        msg = HumanMessage(
            content=f"情景Agent已完成分析。偏向: {scenario.trader_bias}, 库存: {scenario.inventory_signal}, 供应扰动: {scenario.supply_disruption}, 需求热度: {scenario.demand_heat}"
        )

        return {"messages": [msg], "scenario_spec_json": scenario.model_dump_json(indent=2)}

    return scenario_agent_node
