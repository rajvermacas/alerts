"""AG-UI LangGraph Integration.

This module provides integration between AG-UI protocol and LangGraph
using the official ag_ui_langgraph package.

It enables direct streaming from LangGraph agents to AG-UI compatible
frontends like CopilotKit without intermediate A2A protocol translation.

Usage:
    from alerts.agui.langgraph_integration import create_agui_langgraph_endpoint
    from fastapi import FastAPI

    app = FastAPI()

    # Add AG-UI endpoint for LangGraph agent
    create_agui_langgraph_endpoint(app, agent.graph, "/agent")

See: https://pypi.org/project/ag-ui-langgraph/
"""

import logging
from typing import Any, Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Try to import ag_ui_langgraph
try:
    from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
    AGUI_LANGGRAPH_AVAILABLE = True
except ImportError:
    AGUI_LANGGRAPH_AVAILABLE = False
    LangGraphAgent = None
    add_langgraph_fastapi_endpoint = None
    logger.warning(
        "ag_ui_langgraph not installed. Install with: pip install ag-ui-langgraph"
    )


def create_agui_langgraph_endpoint(
    app: FastAPI,
    graph: Any,
    route: str = "/agent",
    **kwargs,
) -> bool:
    """Create an AG-UI endpoint for a LangGraph graph.

    This function wraps ag_ui_langgraph.add_langgraph_fastapi_endpoint
    to add AG-UI protocol support to a FastAPI app.

    Args:
        app: FastAPI application instance
        graph: Compiled LangGraph StateGraph
        route: Route path for the endpoint (default: "/agent")
        **kwargs: Additional arguments passed to add_langgraph_fastapi_endpoint

    Returns:
        True if endpoint was created, False if ag_ui_langgraph is not available

    Example:
        from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent
        from alerts.agui.langgraph_integration import create_agui_langgraph_endpoint

        agent = InsiderTradingAnalyzerAgent(llm, data_dir, output_dir)
        create_agui_langgraph_endpoint(app, agent.graph, "/insider-trading")
    """
    if not AGUI_LANGGRAPH_AVAILABLE:
        logger.error("ag_ui_langgraph is not installed")
        return False

    try:
        add_langgraph_fastapi_endpoint(app, graph, route, **kwargs)
        logger.info(f"Created AG-UI LangGraph endpoint at {route}")
        return True
    except Exception as e:
        logger.error(f"Failed to create AG-UI LangGraph endpoint: {e}")
        return False


def wrap_langgraph_agent(graph: Any, name: str = "alert_analyzer") -> Optional[Any]:
    """Wrap a LangGraph graph in an AG-UI LangGraphAgent.

    This creates a LangGraphAgent that can be used with AG-UI protocol
    for streaming events.

    Args:
        graph: Compiled LangGraph StateGraph
        name: Agent name for identification

    Returns:
        LangGraphAgent instance or None if not available
    """
    if not AGUI_LANGGRAPH_AVAILABLE:
        logger.error("ag_ui_langgraph is not installed")
        return None

    try:
        agent = LangGraphAgent(graph=graph, name=name)
        logger.info(f"Created AG-UI LangGraphAgent: {name}")
        return agent
    except Exception as e:
        logger.error(f"Failed to create LangGraphAgent: {e}")
        return None


def is_agui_langgraph_available() -> bool:
    """Check if ag_ui_langgraph package is available.

    Returns:
        True if ag_ui_langgraph is installed and available
    """
    return AGUI_LANGGRAPH_AVAILABLE
