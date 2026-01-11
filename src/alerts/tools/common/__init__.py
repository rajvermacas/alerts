"""Common tools package for SMARTS Alert Analyzer.

This package contains tools that are shared across multiple agent types
(e.g., insider trading, wash trade). These tools should NEVER be modified
for agent-specific needs - create new tools in agent-specific packages instead.

Architecture Note (AlertReaderTool Removed):
- AlertReaderTool has been removed from this package
- Alert context is now received pre-parsed via request.alert_context
- See: .dev-resources/architecture/remove-alert-reader-tool.md
"""

from alerts.tools.common.base import BaseTool, StreamWriter
# AlertReaderTool REMOVED - context now comes via request.alert_context
from alerts.tools.common.trader_profile import TraderProfileTool
from alerts.tools.common.market_data import MarketDataTool

__all__ = [
    "BaseTool",
    "StreamWriter",
    # "AlertReaderTool" - REMOVED, see architecture doc
    "TraderProfileTool",
    "MarketDataTool",
]
