"""Agents package for SMARTS Alert Analyzer.

This package contains specialized agents for different alert types,
each with their own tools and prompts.
"""

from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent
from alerts.agents.wash_trade.agent import WashTradeAnalyzerAgent

# Backward compatibility alias
AlertAnalyzerAgent = InsiderTradingAnalyzerAgent

__all__ = [
    "InsiderTradingAnalyzerAgent",
    "AlertAnalyzerAgent",  # Backward compatibility
    "WashTradeAnalyzerAgent",
]
