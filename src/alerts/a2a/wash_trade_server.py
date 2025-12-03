"""A2A Server for the Wash Trade Alert Analyzer.

This module provides the A2A server entry point for the wash trade
alert analyzer, exposing it as an A2A-compatible agent.

Supports both standard A2A and message/stream endpoint for SSE streaming.

Usage:
    python -m alerts.a2a.wash_trade_server --host 0.0.0.0 --port 10002
"""

import asyncio
import json
import logging
import sys
import uuid

import click
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv
from sse_starlette import EventSourceResponse
from starlette.requests import Request
from starlette.routing import Route

from alerts.a2a.wash_trade_executor import WashTradeAgentExecutor
from alerts.config import ConfigurationError, get_config, setup_logging
from alerts.llm_factory import create_llm

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global executor reference for streaming endpoint
_executor: WashTradeAgentExecutor | None = None


async def message_stream_endpoint(request: Request):
    """Handle SSE streaming for A2A message/stream requests."""
    global _executor

    if _executor is None:
        return EventSourceResponse(
            _error_generator("Executor not initialized"),
            media_type="text/event-stream",
        )

    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON in request: {e}")
        return EventSourceResponse(
            _error_generator(f"Invalid JSON: {e}"),
            media_type="text/event-stream",
        )

    # Extract alert path from request
    params = body.get("params", {})
    message = params.get("message", {})
    parts = message.get("parts", [])

    alert_path = None
    for part in parts:
        if part.get("type") == "textPart":
            alert_path = part.get("text", "").strip()
            break

    if not alert_path:
        return EventSourceResponse(
            _error_generator("No alert path provided in message"),
            media_type="text/event-stream",
        )

    task_id = str(uuid.uuid4())
    logger.info(f"Starting streaming wash trade analysis for task {task_id}: {alert_path}")

    async def event_generator():
        try:
            async for event in _executor.execute_stream(task_id, alert_path):
                if await request.is_disconnected():
                    logger.info(f"Client disconnected for task {task_id}")
                    break

                yield {
                    "data": json.dumps(event),
                    "event": event.get("result", {}).get("metadata", {}).get("event_type", "update"),
                    "id": event.get("result", {}).get("metadata", {}).get("event_id", str(uuid.uuid4())),
                    "retry": 5000,
                }

                if event.get("result", {}).get("taskStatusUpdateEvent", {}).get("final", False):
                    logger.info(f"Final event sent for task {task_id}")
                    break

                await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for task {task_id}")
        except Exception as e:
            logger.error(f"Stream error for task {task_id}: {e}", exc_info=True)
            yield {
                "data": json.dumps({
                    "jsonrpc": "2.0",
                    "result": {
                        "task": {"id": task_id, "state": "failed"},
                        "taskStatusUpdateEvent": {"task": {"id": task_id, "state": "failed"}, "final": True},
                    },
                }),
                "event": "error",
            }

    return EventSourceResponse(event_generator(), media_type="text/event-stream")


async def _error_generator(error_message: str):
    yield {
        "data": json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": error_message}}),
        "event": "error",
    }


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
        global _executor
        executor = WashTradeAgentExecutor(
            llm=llm,
            data_dir=config.data.data_dir,
            output_dir=config.data.output_dir,
        )
        _executor = executor

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

        # Build the app and add streaming route
        app = server.build()
        app.routes.append(
            Route("/message/stream", message_stream_endpoint, methods=["POST"])
        )

        logger.info(f"Wash Trade Server starting at http://{host}:{port}")
        logger.info(f"Agent card available at http://{host}:{port}/.well-known/agent.json")
        logger.info(f"Streaming endpoint: POST http://{host}:{port}/message/stream")

        # Run server
        uvicorn.run(app, host=host, port=port)

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Server startup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
