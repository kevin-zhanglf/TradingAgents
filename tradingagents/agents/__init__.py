from .utils.agent_utils import create_msg_delete
from .utils.agent_states import AgentState, InvestDebateState, RiskDebateState

from .analysts.fundamentals_analyst import create_fundamentals_analyst
from .analysts.market_analyst import create_market_analyst
from .analysts.news_analyst import create_news_analyst
from .analysts.social_media_analyst import create_social_media_analyst

from .researchers.bear_researcher import create_bear_researcher
from .researchers.bull_researcher import create_bull_researcher

from .risk_mgmt.aggressive_debator import create_aggressive_debator
from .risk_mgmt.conservative_debator import create_conservative_debator
from .risk_mgmt.neutral_debator import create_neutral_debator

from .managers.research_manager import create_research_manager
from .managers.portfolio_manager import create_portfolio_manager

from .trader.trader import create_trader

from .chem_analysts import (
    create_chain_price_analyst,
    create_supply_demand_analyst,
    create_news_policy_analyst,
    create_demand_heat_analyst,
    create_model_agent,
    create_scenario_agent,
)
from .chem_managers import create_forecast_synthesizer

__all__ = [
    "AgentState",
    "create_msg_delete",
    "InvestDebateState",
    "RiskDebateState",
    "create_bear_researcher",
    "create_bull_researcher",
    "create_research_manager",
    "create_fundamentals_analyst",
    "create_market_analyst",
    "create_neutral_debator",
    "create_news_analyst",
    "create_aggressive_debator",
    "create_portfolio_manager",
    "create_conservative_debator",
    "create_social_media_analyst",
    "create_trader",
    # Chemical plastics agents
    "create_chain_price_analyst",
    "create_supply_demand_analyst",
    "create_news_policy_analyst",
    "create_demand_heat_analyst",
    "create_model_agent",
    "create_scenario_agent",
    "create_forecast_synthesizer",
]
