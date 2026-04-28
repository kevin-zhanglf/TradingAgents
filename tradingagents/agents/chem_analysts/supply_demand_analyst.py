"""Supply-demand analyst for ABS chemical plastics forecasting."""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.chem_fundamental_tools import get_inventory, get_operating_rate, get_import_export


def create_supply_demand_analyst(llm):
    """Create a supply-demand analyst node."""

    def supply_demand_analyst_node(state):
        grade = state.get("grade_of_interest", "ABS-3001MF2")
        region = state.get("region", "华北")
        asof_date = state.get("asof_date", "2025-01-15")

        tools = [get_inventory, get_operating_rate, get_import_export]

        system_message = f"""你是一位专业的化塑供需基本面分析师，专注于ABS树脂市场供需平衡。

分析对象：{grade}，{region}市场，基准日期：{asof_date}

请完成以下分析任务：

1. **库存分析**：调用 get_inventory 获取ABS库存数据（product="ABS", region="{region}"），分析库存绝对量、库存天数及同比变化。库存偏高（>90天）为利空信号，偏低（<45天）为利多信号。

2. **开工率分析**：调用 get_operating_rate 获取ABS装置开工率数据，判断供给端压力。开工率>85%为高供给压力，<65%为供给偏紧。

3. **进出口分析**：调用 get_import_export 分别查询ABS进口（trade_type="import"）数据，分析进口量变化对国内供应的影响。

4. **供需平衡判断**：综合库存、开工率、进口量给出供需平衡信号：
   - 偏紧（库存低 + 开工率低 + 进口减少）→ 价格利多
   - 偏松（库存高 + 开工率高 + 进口增加）→ 价格利空
   - 中性 → 供需基本平衡

请用中文输出量化分析报告，重点给出明确的供需信号判断。"""

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "你是专业化工品供需分析助手。使用提供的工具完成供需基本面分析。"
                " 工具: {tool_names}.\n{system_message}"
                " 分析基准日期: {asof_date}.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(asof_date=asof_date)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {"messages": [result], "supply_demand_report": report}

    return supply_demand_analyst_node
