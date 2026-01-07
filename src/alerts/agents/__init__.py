"""Agents package for SMARTS Alert Analyzer.

This package contains specialized agents for different alert types,
each with their own tools and prompts.

All agents now use deterministic execution with fixed tool order
for Proactive Information Flow architecture.
"""

from alerts.agents.insider_trading import (
    DeterministicInsiderTradingAgent,
    InsiderTradingAnalyzerAgent,
)
from alerts.agents.wash_trade import (
    DeterministicWashTradeAgent,
    WashTradeAnalyzerAgent,
)

# Backward compatibility alias
AlertAnalyzerAgent = InsiderTradingAnalyzerAgent

__all__ = [
    "DeterministicInsiderTradingAgent",
    "InsiderTradingAnalyzerAgent",
    "DeterministicWashTradeAgent",
    "WashTradeAnalyzerAgent",
    "AlertAnalyzerAgent",  # Backward compatibility
]
