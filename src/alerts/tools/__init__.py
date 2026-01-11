"""Tools package for SMARTS Alert Analyzer.

This package contains all tools used by the LangGraph agents
to gather and interpret evidence for alert analysis.

Tools are organized into:
- tools/common/: Shared tools used by multiple agent types
- agents/{type}/tools/: Agent-specific tools

This module re-exports tools for backward compatibility.
New code should import from specific packages.

Architecture Note (AlertReaderTool Removed):
- AlertReaderTool has been removed from this package
- Alert context is now received pre-parsed via request.alert_context
- See: .dev-resources/architecture/remove-alert-reader-tool.md
"""

# Common tools (shared across agents)
# NOTE: AlertReaderTool REMOVED - context now comes via request.alert_context
from alerts.tools.common import (
    BaseTool,
    StreamWriter,
    TraderProfileTool,
    MarketDataTool,
)

# Insider trading specific tools (backward compatibility)
from alerts.agents.insider_trading.tools import (
    TraderHistoryTool,
    MarketNewsTool,
)

__all__ = [
    # Base classes
    "BaseTool",
    "StreamWriter",
    # Common tools (AlertReaderTool REMOVED - see architecture doc)
    "TraderProfileTool",
    "MarketDataTool",
    # Insider trading specific (backward compatibility)
    "TraderHistoryTool",
    "MarketNewsTool",
]
