"""LangGraph agent for SMARTS Alert Analyzer.

This module re-exports the InsiderTradingAnalyzerAgent for backward
compatibility. New code should import from alerts.agents.

Agent structure:
- alerts.agents.insider_trading: Insider trading analyzer agent
- alerts.agents.wash_trade: Wash trade analyzer agent (coming soon)
"""

# Re-export from new location for backward compatibility
from alerts.agents.insider_trading.agent import (
    InsiderTradingAnalyzerAgent,
    AlertAnalyzerAgent,  # Backward compatibility alias
    ReadAlertArgs,
    QueryTraderHistoryArgs,
    QueryTraderProfileArgs,
    QueryMarketNewsArgs,
    QueryMarketDataArgs,
    QueryPeerTradesArgs,
)

__all__ = [
    "InsiderTradingAnalyzerAgent",
    "AlertAnalyzerAgent",
    "ReadAlertArgs",
    "QueryTraderHistoryArgs",
    "QueryTraderProfileArgs",
    "QueryMarketNewsArgs",
    "QueryMarketDataArgs",
    "QueryPeerTradesArgs",
]
