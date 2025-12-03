"""Tools package for SMARTS Alert Analyzer.

This package contains all tools used by the LangGraph agents
to gather and interpret evidence for alert analysis.

Tools are organized into:
- tools/common/: Shared tools used by multiple agent types
- agents/{type}/tools/: Agent-specific tools

This module re-exports tools for backward compatibility.
New code should import from specific packages.
"""

# Common tools (shared across agents)
from alerts.tools.common import (
    BaseTool,
    DataLoadingMixin,
    AlertReaderTool,
    TraderProfileTool,
    MarketDataTool,
)

# Insider trading specific tools (backward compatibility)
from alerts.agents.insider_trading.tools import (
    TraderHistoryTool,
    MarketNewsTool,
    PeerTradesTool,
)

__all__ = [
    # Base classes
    "BaseTool",
    "DataLoadingMixin",
    # Common tools
    "AlertReaderTool",
    "TraderProfileTool",
    "MarketDataTool",
    # Insider trading specific (backward compatibility)
    "TraderHistoryTool",
    "MarketNewsTool",
    "PeerTradesTool",
]
