"""A2A (Agent-to-Agent) protocol integration for SMARTS Alert Analyzer.

This module provides A2A server and client implementations for
orchestrating multiple specialized agents for alert analysis.

Architecture:
    The A2A integration follows a hub-and-spoke model:

    ┌─────────────────────────────────────────────────────────────────┐
    │                     Orchestrator Agent (Port 10000)             │
    │  (Reads alerts, determines type, routes to specialized agents)  │
    └───────────────────────────┬─────────────────────────────────────┘
                                │ A2A Protocol
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
    ┌───────────────────────────┐   ┌───────────────────────────────┐
    │   Insider Trading Agent   │   │     Wash Trade Agent          │
    │      (Port 10001)         │   │       (Port 10002)            │
    └───────────────────────────┘   └───────────────────────────────┘

Usage:
    # Start the insider trading agent server (in terminal 1)
    python -m alerts.a2a.insider_trading_server --port 10001

    # Start the wash trade agent server (in terminal 2)
    python -m alerts.a2a.wash_trade_server --port 10002

    # Start the orchestrator server (in terminal 3)
    python -m alerts.a2a.orchestrator_server --port 10000

    # Or use the convenience scripts
    alerts-insider-trading-server
    alerts-wash-trade-server
    alerts-orchestrator-server
"""

__all__ = [
    "InsiderTradingAgentExecutor",
    "WashTradeAgentExecutor",
    "OrchestratorAgent",
    "OrchestratorAgentExecutor",
]


def __getattr__(name: str):
    """Lazy import to avoid circular imports."""
    if name == "InsiderTradingAgentExecutor":
        from alerts.a2a.insider_trading_executor import InsiderTradingAgentExecutor
        return InsiderTradingAgentExecutor
    elif name == "WashTradeAgentExecutor":
        from alerts.a2a.wash_trade_executor import WashTradeAgentExecutor
        return WashTradeAgentExecutor
    elif name == "OrchestratorAgent":
        from alerts.a2a.orchestrator import OrchestratorAgent
        return OrchestratorAgent
    elif name == "OrchestratorAgentExecutor":
        from alerts.a2a.orchestrator_executor import OrchestratorAgentExecutor
        return OrchestratorAgentExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
