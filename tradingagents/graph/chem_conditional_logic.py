"""Conditional logic for chemical plastics forecast graph."""
from tradingagents.agents.utils.agent_states import AgentState


class ChemConditionalLogic:
    """Handles conditional routing for the chemical forecast graph."""

    def should_continue_chain_price(self, state: AgentState) -> str:
        """Route chain price analyst: tools loop or move forward."""
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools_chain_price"
        return "Msg Clear Chain Price"

    def should_continue_supply_demand(self, state: AgentState) -> str:
        """Route supply/demand analyst: tools loop or move forward."""
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools_supply_demand"
        return "Msg Clear Supply Demand"

    def should_continue_news_policy(self, state: AgentState) -> str:
        """Route news/policy analyst: tools loop or move forward."""
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools_news_policy"
        return "Msg Clear News Policy"

    def should_continue_demand_heat(self, state: AgentState) -> str:
        """Route demand heat analyst: tools loop or move forward."""
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools_demand_heat"
        return "Msg Clear Demand Heat"
