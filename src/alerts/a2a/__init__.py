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
                                ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │           Insider Trading Agent A2A Server (Port 10001)         │
    │  (Existing AlertAnalyzerAgent exposed via A2A)                  │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    # Start the insider trading agent server (in terminal 1)
    python -m alerts.a2a.insider_trading_server --port 10001

    # Start the orchestrator server (in terminal 2)
    python -m alerts.a2a.orchestrator_server --port 10000

    # Or use the convenience scripts
    alerts-insider-trading-server
    alerts-orchestrator-server
"""

from alerts.a2a.insider_trading_executor import InsiderTradingAgentExecutor
from alerts.a2a.orchestrator import OrchestratorAgent
from alerts.a2a.orchestrator_executor import OrchestratorAgentExecutor

__all__ = [
    "InsiderTradingAgentExecutor",
    "OrchestratorAgent",
    "OrchestratorAgentExecutor",
]
