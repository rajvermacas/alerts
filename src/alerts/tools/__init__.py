"""Tools package for SMARTS Alert Analyzer.

This package contains all tools used by the LangGraph agent
to gather and interpret evidence for alert analysis.
"""

from alerts.tools.alert_reader import AlertReaderTool
from alerts.tools.market_data import MarketDataTool
from alerts.tools.market_news import MarketNewsTool
from alerts.tools.peer_trades import PeerTradesTool
from alerts.tools.trader_history import TraderHistoryTool
from alerts.tools.trader_profile import TraderProfileTool

__all__ = [
    "AlertReaderTool",
    "TraderHistoryTool",
    "TraderProfileTool",
    "MarketNewsTool",
    "MarketDataTool",
    "PeerTradesTool",
]
