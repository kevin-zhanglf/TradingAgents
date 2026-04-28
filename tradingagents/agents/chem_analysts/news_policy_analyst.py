"""News and policy analyst for ABS chemical plastics forecasting."""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.chem_news_tools import search_chem_news, search_policy_news


def create_news_policy_analyst(llm):
    """Create a news and policy analyst node."""

    def news_policy_analyst_node(state):
        grade = state.get("grade_of_interest", "ABS-3001MF2")
        region = state.get("region", "华北")
        asof_date = state.get("asof_date", "2025-01-15")

        tools = [search_chem_news, search_policy_news]

        system_message = f"""你是一位专业的化塑市场资讯与政策分析师，关注ABS树脂市场动态。

分析对象：{grade}，{region}市场，基准日期：{asof_date}

请完成以下分析任务：

1. **行业新闻扫描**：调用 search_chem_news，搜索"ABS供需 {region}"相关新闻（时间范围：基准日期前30天），识别：
   - 供应扰动事件（如装置停产检修、物流中断）
   - 需求变化信号（家电、汽车行业备货动态）
   - 进出口贸易变化（韩国/台湾ABS进口动态）
   - 竞品替代动态（PS、SAN价格及需求切换）

2. **政策动态分析**：调用 search_policy_news，搜索"ABS反倾销 化工政策"（时间范围：基准日期前90天），识别：
   - 贸易政策（反倾销、进口配额）
   - 环保/安全监管政策
   - 下游行业扶持政策（家电下乡、新能源汽车补贴）

3. **事件影响评估**：对每个重要事件评估：
   - 价格方向影响（利多/利空/中性）
   - 影响强度（强/中/弱）
   - 预计持续时间

4. **综合结论**：是否存在重大供应扰动？近期是否有重大政策利多/利空？

使用中文输出详细分析报告。"""

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "你是专业化工品资讯与政策分析助手。使用工具完成新闻和政策分析。"
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

        return {"messages": [result], "news_policy_report": report}

    return news_policy_analyst_node
