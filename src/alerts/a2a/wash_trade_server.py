"""A2A Server for the Wash Trade Alert Analyzer.

This module provides the A2A server entry point for the wash trade
alert analyzer, exposing it as an A2A-compatible agent.

Usage:
    python -m alerts.a2a.wash_trade_server --host 0.0.0.0 --port 10002
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
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from alerts.a2a.wash_trade_executor import WashTradeAgentExecutor
from alerts.config import ConfigurationError, get_config, setup_logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_llm(config):
    """Create LLM instance based on configuration.

    Args:
        config: AppConfig instance

    Returns:
        LangChain LLM instance
    """
    logger.info(f"Creating LLM with provider: {config.llm.provider}")

    if config.llm.is_azure():
        logger.info(f"Using Azure OpenAI: {config.llm.azure_endpoint}")
        return AzureChatOpenAI(
            azure_deployment=config.llm.model,
            azure_endpoint=config.llm.azure_endpoint,
            api_version=config.llm.azure_api_version,
            api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
    elif config.llm.provider == "openrouter":
        logger.info(f"Using OpenRouter: {config.llm.model}")
        default_headers = {}
        if config.llm.openrouter_site_url:
            default_headers["HTTP-Referer"] = config.llm.openrouter_site_url
        if config.llm.openrouter_site_name:
            default_headers["X-Title"] = config.llm.openrouter_site_name

        return ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=default_headers if default_headers else None,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
    else:
        logger.info(f"Using OpenAI: {config.llm.model}")
        return ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )


@click.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=10002, help="Port to bind to")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(host: str, port: int, verbose: bool) -> None:
    """Start the Wash Trade Alert Analyzer A2A server."""
    try:
        # Load configuration
        config = get_config()

        # Setup logging
        if verbose:
            config.logging.level = "DEBUG"
        setup_logging(config.logging)

        logger.info("=" * 60)
        logger.info("Starting Wash Trade Alert Analyzer A2A Server")
        logger.info("=" * 60)

        # Create LLM
        llm = create_llm(config)

        # Define agent skill
        skill = AgentSkill(
            id="analyze_wash_trade_alert",
            name="Wash Trade Alert Analysis",
            description=(
                "Analyzes SMARTS surveillance alerts for potential wash trading violations. "
                "Uses a fully agentic LLM-based approach to detect same beneficial ownership, "
                "coordinated timing patterns, circular trade flows, and artificial volume creation. "
                "Applies APAC regulatory framework (MAS SFA, SFC SFO, ASIC, FSA FIEA)."
            ),
            tags=["wash trade", "compliance", "alert analysis", "surveillance", "APAC"],
            examples=[
                "Analyze the wash trade alert at test_data/alerts/wash_trade/wash_genuine.xml",
                "Check this alert for wash trading: test_data/alerts/wash_trade/wash_false_positive.xml",
                "Review wash_layered.xml for circular trading patterns",
            ],
        )

        # Define agent card
        agent_card = AgentCard(
            name="Wash Trade Alert Analyzer",
            description=(
                "An intelligent compliance filter that analyzes SMARTS surveillance "
                "alerts for potential wash trading violations. Detects same beneficial "
                "ownership on both sides of trades, pre-arranged execution patterns, "
                "circular trade flows (A->B->C->A), and artificial volume creation. "
                "Uses APAC regulatory framework including Singapore MAS SFA, Hong Kong "
                "SFC SFO, Australia ASIC, and Japan FSA FIEA."
            ),
            url=f"http://{host}:{port}/",
            version="1.0.0",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=True),
            skills=[skill],
        )

        # Create executor
        executor = WashTradeAgentExecutor(
            llm=llm,
            data_dir=config.data.data_dir,
            output_dir=config.data.output_dir,
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

        logger.info(f"Wash Trade Server starting at http://{host}:{port}")
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
