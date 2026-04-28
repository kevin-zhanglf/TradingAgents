"""Demand heat analyst for ABS chemical plastics forecasting."""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.chem_trade_tools import get_quote_activity, get_deal_activity


def create_demand_heat_analyst(llm):
    """Create a demand heat analyst node."""

    def demand_heat_analyst_node(state):
        grade = state.get("grade_of_interest", "ABS-3001MF2")
        region = state.get("region", "华北")
        asof_date = state.get("asof_date", "2025-01-15")

        tools = [get_quote_activity, get_deal_activity]

        system_message = f"""你是一位专业的化塑市场需求热度分析师，专注于ABS成交活跃度分析。

分析对象：{grade}，{region}市场，基准日期：{asof_date}

请完成以下分析任务：

1. **报价活跃度分析**：调用 get_quote_activity 获取近30天报价数据，分析：
   - 日均报价笔数趋势（上升=需求热度增加）
   - 买卖价差（Bid-Ask Spread）变化（缩窄=流动性改善）
   - 报价修改频率（频繁修改=市场不确定性高）
   - 活跃报价商数量

2. **成交活跃度分析**：调用 get_deal_activity 获取近30天成交数据，分析：
   - 日均成交笔数和成交量（体积）趋势
   - 平均成交价格走势
   - 报价转成交率（成交率高=需求真实旺盛）
   - 成交价与报价的折扣幅度（折扣收窄=买家议价空间下降）

3. **需求热度判断**：
   - 强（Strong）：成交量↑ + 成交率↑ + 折扣收窄 + 报价笔数↑
   - 弱（Weak）：成交量↓ + 成交率↓ + 折扣扩大 + 报价稀疏
   - 中性（Normal）：混合信号

4. **结论**：当前市场需求热度评级，对价格的影响判断。

使用中文输出量化分析报告。"""

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "你是专业化工品市场需求热度分析助手。使用工具分析成交活跃度。"
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

        return {"messages": [result], "demand_heat_report": report}

    return demand_heat_analyst_node
