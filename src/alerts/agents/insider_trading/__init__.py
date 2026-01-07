"""Insider trading agent package.

This package contains the insider trading analyzer agent and its
specific tools, prompts, and models.

Uses DeterministicInsiderTradingAgent with fixed tool execution order
for Proactive Information Flow architecture.
"""

from alerts.agents.insider_trading.deterministic_agent import (
    DeterministicInsiderTradingAgent,
    TOOL_ORDER as IT_TOOL_ORDER,
)

# Backward compatibility alias
InsiderTradingAnalyzerAgent = DeterministicInsiderTradingAgent

__all__ = [
    "DeterministicInsiderTradingAgent",
    "InsiderTradingAnalyzerAgent",  # Backward compatibility
    "IT_TOOL_ORDER",
]
