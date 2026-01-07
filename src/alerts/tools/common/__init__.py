"""Common tools package for SMARTS Alert Analyzer.

This package contains tools that are shared across multiple agent types
(e.g., insider trading, wash trade). These tools should NEVER be modified
for agent-specific needs - create new tools in agent-specific packages instead.

In Proactive Info Flow mode, all tools receive data via execute(data=...)
instead of loading their own data internally.
"""

from alerts.tools.common.base import (
    BaseTool,
    DataLoadingMixin,
    StreamWriter,
    DataFormat,
    ToolDataError,
    MissingInjectedDataError,
    InvalidDataFormatError,
)
from alerts.tools.common.alert_reader import AlertReaderTool
from alerts.tools.common.trader_profile import TraderProfileTool
from alerts.tools.common.market_data import MarketDataTool

__all__ = [
    # Base classes and types
    "BaseTool",
    "DataLoadingMixin",
    "StreamWriter",
    "DataFormat",
    # Exceptions
    "ToolDataError",
    "MissingInjectedDataError",
    "InvalidDataFormatError",
    # Tools
    "AlertReaderTool",
    "TraderProfileTool",
    "MarketDataTool",
]
