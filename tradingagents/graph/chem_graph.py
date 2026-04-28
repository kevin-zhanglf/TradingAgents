"""Chemical plastics price forecasting graph."""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState, RiskDebateState
from tradingagents.agents.utils.agent_utils import create_msg_delete
from tradingagents.agents.chem_analysts import (
    create_chain_price_analyst,
    create_supply_demand_analyst,
    create_news_policy_analyst,
    create_demand_heat_analyst,
    create_model_agent,
    create_scenario_agent,
)
from tradingagents.agents.chem_managers import create_forecast_synthesizer
from tradingagents.agents.utils.chem_price_tools import get_chem_price_series, get_upstream_price_series
from tradingagents.agents.utils.chem_fundamental_tools import get_inventory, get_operating_rate, get_import_export
from tradingagents.agents.utils.chem_news_tools import search_chem_news, search_policy_news
from tradingagents.agents.utils.chem_trade_tools import get_quote_activity, get_deal_activity
from tradingagents.chem_schemas import FinalForecast, BaseForecast, PriceForecastPoint
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client

from .chem_conditional_logic import ChemConditionalLogic

logger = logging.getLogger(__name__)


class ChemForecastGraph:
    """Chemical plastics price forecasting graph."""

    def __init__(
        self,
        selected_analysts: List[str] = None,
        debug: bool = False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        if selected_analysts is None:
            selected_analysts = ["chain_price", "supply_demand", "news_policy", "demand_heat"]

        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config or DEFAULT_CONFIG.copy()
        self.callbacks = callbacks or []

        llm_kwargs = {}
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config.get("llm_provider", "openai"),
            model=self.config.get("deep_think_llm", "gpt-4o-mini"),
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config.get("llm_provider", "openai"),
            model=self.config.get("quick_think_llm", "gpt-4o-mini"),
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        self.conditional_logic = ChemConditionalLogic()
        self.tool_nodes = self._create_chem_tool_nodes()
        self.workflow = self._setup_chem_graph(selected_analysts)
        self.graph = self.workflow.compile()

    def _create_chem_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for each analyst type."""
        return {
            "chain_price": ToolNode([get_chem_price_series, get_upstream_price_series]),
            "supply_demand": ToolNode([get_inventory, get_operating_rate, get_import_export]),
            "news_policy": ToolNode([search_chem_news, search_policy_news]),
            "demand_heat": ToolNode([get_quote_activity, get_deal_activity]),
        }

    def _setup_chem_graph(self, selected_analysts: List[str]) -> StateGraph:
        """Wire the chemical forecast graph."""
        workflow = StateGraph(AgentState)

        analyst_factory = {
            "chain_price": lambda: create_chain_price_analyst(self.quick_thinking_llm),
            "supply_demand": lambda: create_supply_demand_analyst(self.quick_thinking_llm),
            "news_policy": lambda: create_news_policy_analyst(self.quick_thinking_llm),
            "demand_heat": lambda: create_demand_heat_analyst(self.quick_thinking_llm),
        }

        cond_method_map = {
            "chain_price": self.conditional_logic.should_continue_chain_price,
            "supply_demand": self.conditional_logic.should_continue_supply_demand,
            "news_policy": self.conditional_logic.should_continue_news_policy,
            "demand_heat": self.conditional_logic.should_continue_demand_heat,
        }

        label_map = {
            "chain_price": "Chain Price",
            "supply_demand": "Supply Demand",
            "news_policy": "News Policy",
            "demand_heat": "Demand Heat",
        }

        for analyst_type in selected_analysts:
            if analyst_type not in analyst_factory:
                continue
            label = label_map[analyst_type]
            workflow.add_node(f"{label} Analyst", analyst_factory[analyst_type]())
            workflow.add_node(f"Msg Clear {label}", create_msg_delete())
            workflow.add_node(f"tools_{analyst_type}", self.tool_nodes[analyst_type])

        workflow.add_node("Model Agent", create_model_agent(self.quick_thinking_llm))
        workflow.add_node("Scenario Agent", create_scenario_agent(self.deep_thinking_llm))
        workflow.add_node("Forecast Synthesizer", create_forecast_synthesizer(self.deep_thinking_llm))

        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{label_map[first_analyst]} Analyst")

        for i, analyst_type in enumerate(selected_analysts):
            if analyst_type not in label_map:
                continue
            label = label_map[analyst_type]
            current_node = f"{label} Analyst"
            tools_node = f"tools_{analyst_type}"
            clear_node = f"Msg Clear {label}"

            workflow.add_conditional_edges(
                current_node,
                cond_method_map[analyst_type],
                [tools_node, clear_node],
            )
            workflow.add_edge(tools_node, current_node)

            if i < len(selected_analysts) - 1:
                next_label = label_map[selected_analysts[i + 1]]
                workflow.add_edge(clear_node, f"{next_label} Analyst")
            else:
                workflow.add_edge(clear_node, "Model Agent")

        workflow.add_edge("Model Agent", "Scenario Agent")
        workflow.add_edge("Scenario Agent", "Forecast Synthesizer")
        workflow.add_edge("Forecast Synthesizer", END)

        return workflow

    def _create_initial_state(
        self,
        grade: str,
        region: str,
        price_type: str,
        asof_date: str,
        scenario_input: str = "",
    ) -> Dict[str, Any]:
        """Initialize the AgentState for a chemical forecast run."""
        return {
            "messages": [("human", f"请分析{grade}在{region}市场的{price_type}价格，预测日期：{asof_date}")],
            # Chem-specific fields
            "grade_of_interest": grade,
            "region": region,
            "price_type": price_type,
            "asof_date": asof_date,
            "scenario_input": scenario_input,
            # Report fields (empty initially)
            "chain_price_report": "",
            "supply_demand_report": "",
            "news_policy_report": "",
            "demand_heat_report": "",
            # Forecast fields (empty initially)
            "base_forecast_json": "",
            "scenario_spec_json": "",
            "final_forecast_json": "",
            # Stock fields required by AgentState (set to empty/defaults)
            "company_of_interest": grade,
            "trade_date": asof_date,
            "sender": "",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": InvestDebateState({
                "bull_history": "",
                "bear_history": "",
                "history": "",
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            }),
            "investment_plan": "",
            "trader_investment_plan": "",
            "risk_debate_state": RiskDebateState({
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "history": "",
                "latest_speaker": "",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            }),
            "final_trade_decision": "",
            "past_context": "",
        }

    def propagate(
        self,
        grade: str,
        region: str,
        price_type: str,
        asof_date: str,
        scenario_input: str = "",
    ) -> Tuple[Dict[str, Any], FinalForecast]:
        """Run the chemical forecast graph.

        Args:
            grade: Chemical grade e.g. "ABS-3001MF2"
            region: Market region e.g. "华北"
            price_type: "deal" or "quote"
            asof_date: Analysis date YYYY-MM-DD
            scenario_input: Optional trader scenario text in Chinese

        Returns:
            (final_state, FinalForecast)
        """
        init_state = self._create_initial_state(grade, region, price_type, asof_date, scenario_input)
        args = {
            "stream_mode": "values",
            "config": {"recursion_limit": self.config.get("max_recur_limit", 100)},
        }

        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_state, **args):
                if chunk.get("messages"):
                    chunk["messages"][-1].pretty_print()
                trace.append(chunk)
            final_state = trace[-1] if trace else init_state
        else:
            final_state = self.graph.invoke(init_state, **args)

        final_forecast_json = final_state.get("final_forecast_json", "")
        if final_forecast_json:
            final_forecast = FinalForecast.model_validate_json(final_forecast_json)
        else:
            base_dt = datetime.strptime(asof_date, "%Y-%m-%d")
            fallback_points = [
                PriceForecastPoint(
                    date=(base_dt + timedelta(days=d)).strftime("%Y-%m-%d"),
                    p10=13000.0,
                    p50=13500.0,
                    p90=14000.0,
                )
                for d in range(1, 31)
            ]
            base = BaseForecast(
                grade=grade,
                region=region,
                price_type=price_type,
                asof_date=asof_date,
                horizon_days=30,
                forecast=fallback_points,
                key_drivers=["数据获取失败，使用默认值"],
                model_name="fallback",
                confidence_note="图执行异常，使用回退预测",
            )
            final_forecast = FinalForecast(base_forecast=base, forecast=fallback_points)

        return final_state, final_forecast
