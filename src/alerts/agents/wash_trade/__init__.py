"""Wash Trade Analyzer Agent package.

This package contains the WashTradeAnalyzerAgent and its
specialized tools for detecting wash trading violations.

Uses DeterministicWashTradeAgent with fixed tool execution order
for Proactive Information Flow architecture.
"""

from alerts.agents.wash_trade.deterministic_agent import (
    DeterministicWashTradeAgent,
    TOOL_ORDER as WT_TOOL_ORDER,
)

# Backward compatibility alias
WashTradeAnalyzerAgent = DeterministicWashTradeAgent

__all__ = [
    "DeterministicWashTradeAgent",
    "WashTradeAnalyzerAgent",  # Backward compatibility
    "WT_TOOL_ORDER",
]
