"""Chain price analyst for ABS chemical plastics forecasting."""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.chem_price_tools import get_chem_price_series, get_upstream_price_series


def create_chain_price_analyst(llm):
    """Create a chain price analyst node for ABS price trend analysis."""

    def chain_price_analyst_node(state):
        grade = state.get("grade_of_interest", "ABS-3001MF2")
        region = state.get("region", "华北")
        price_type = state.get("price_type", "deal")
        asof_date = state.get("asof_date", "2025-01-15")

        tools = [get_chem_price_series, get_upstream_price_series]

        system_message = f"""你是一位专业的化塑产业链价格分析师，专注于ABS树脂市场。

你的任务是分析 {grade}（{region}，{price_type}价）的近期价格趋势及上游成本传导。

请按以下步骤分析（基准日期：{asof_date}）：

1. **目标品种价格走势**：调用 get_chem_price_series 获取过去30天的 {grade} {region} {price_type}价格数据，分析趋势、波动率、近期变化幅度。

2. **上游成本分析**：调用 get_upstream_price_series 分别获取苯乙烯（styrene）、丁二烯（butadiene）、丙烯腈（acrylonitrile）的近30天价格数据，计算它们对ABS成本的影响权重（参考配比：苯乙烯约55%、丁二烯约25%、丙烯腈约20%）。

3. **成本-价格价差**：计算ABS实际价格与理论成本的价差（加工差）变化趋势，判断当前利润空间是否支撑产能。

4. **趋势判断**：给出价格方向的初步判断（偏多/中性/偏空），附具体数据支撑。

请提供详细的数量化分析报告，包含：
- 价格区间统计（最高/最低/均价/最新价）
- 各上游单体价格及对ABS成本贡献
- 近7日、近30日价格变化幅度
- 当前市场价格与成本的关系

使用中文输出报告。"""

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "你是一位专业的化工品市场分析助手，与其他分析师协同工作。"
                " 使用提供的工具完成分析任务。"
                " 你有以下工具可用: {tool_names}.\n{system_message}"
                " 当前分析基准日期: {asof_date}.",
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

        return {"messages": [result], "chain_price_report": report}

    return chain_price_analyst_node
