"""A2A Server for the Orchestrator Agent.

This module provides the A2A server entry point for the orchestrator agent,
which routes alerts to specialized agents.

Usage:
    python -m alerts.a2a.orchestrator_server --host 0.0.0.0 --port 10000

Note: The Insider Trading Agent server must be running before starting
the orchestrator server.
"""

import logging
import sys
from pathlib import Path

import click
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv

from alerts.a2a.orchestrator_executor import OrchestratorAgentExecutor
from alerts.config import ConfigurationError, get_config, setup_logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=10000, help="Port to bind to")
@click.option(
    "--insider-trading-url",
    default="http://localhost:10001",
    help="URL of the insider trading agent A2A server",
)
@click.option(
    "--wash-trade-url",
    default="http://localhost:10002",
    help="URL of the wash trade agent A2A server",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(host: str, port: int, insider_trading_url: str, wash_trade_url: str, verbose: bool) -> None:
    """Start the Orchestrator Agent A2A server."""
    try:
        # Load configuration
        config = get_config()

        # Setup logging
        if verbose:
            config.logging.level = "DEBUG"
        setup_logging(config.logging)

        logger.info("=" * 60)
        logger.info("Starting Orchestrator Agent A2A Server")
        logger.info("=" * 60)
        logger.info(f"Insider Trading Agent URL: {insider_trading_url}")
        logger.info(f"Wash Trade Agent URL: {wash_trade_url}")

        # Define agent skills
        route_skill = AgentSkill(
            id="route_alert",
            name="Route Alert to Specialized Agent",
            description=(
                "Reads an alert file, determines its type, and routes it to "
                "the appropriate specialized agent for analysis. Supports routing "
                "insider trading alerts to the Insider Trading Agent and wash trade "
                "alerts to the Wash Trade Agent."
            ),
            tags=["routing", "orchestration", "alert analysis", "insider trading", "wash trade"],
            examples=[
                "Analyze the alert at test_data/alerts/alert_genuine.xml",
                "Route this alert: test_data/alerts/alert_false_positive.xml",
                "Process alert_ambiguous.xml",
                "Analyze wash trade alert: test_data/alerts/wash_trade/wash_genuine.xml",
            ],
        )

        # Define agent card
        agent_card = AgentCard(
            name="Alert Orchestrator",
            description=(
                "An orchestrator agent that reads surveillance alerts and routes them "
                "to specialized agents for analysis. It determines the alert type and "
                "delegates to the appropriate agent (Insider Trading Agent or Wash Trade "
                "Agent) using the A2A protocol for agent-to-agent communication."
            ),
            url=f"http://{host}:{port}/",
            version="1.0.0",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[route_skill],
        )

        # Create executor
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url=insider_trading_url,
            wash_trade_agent_url=wash_trade_url,
            data_dir=config.data.data_dir,
        )

        # Create request handler
        request_handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
        )

        # Create A2A server
        server = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler,
        )

        logger.info(f"Server starting at http://{host}:{port}")
        logger.info(f"Agent card available at http://{host}:{port}/.well-known/agent.json")

        # Run server
        uvicorn.run(server.build(), host=host, port=port)

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Server startup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
