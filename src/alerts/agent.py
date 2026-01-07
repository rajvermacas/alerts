"""Agent module for SMARTS Alert Analyzer.

This module re-exports the DeterministicInsiderTradingAgent for backward
compatibility. New code should import from alerts.agents.

Agent structure:
- alerts.agents.insider_trading: Insider trading analyzer agent (deterministic)
- alerts.agents.wash_trade: Wash trade analyzer agent (deterministic)

Note: Legacy LangGraph-based agents have been removed in favor of
deterministic agents for Proactive Information Flow architecture.
"""

# Re-export from new location for backward compatibility
from alerts.agents.insider_trading import (
    DeterministicInsiderTradingAgent,
    InsiderTradingAnalyzerAgent,  # Backward compatibility alias (same as Deterministic)
)

# Backward compatibility alias
AlertAnalyzerAgent = InsiderTradingAnalyzerAgent

__all__ = [
    "DeterministicInsiderTradingAgent",
    "InsiderTradingAnalyzerAgent",
    "AlertAnalyzerAgent",
]
