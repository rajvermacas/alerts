"""A2A Server for the Orchestrator Agent.

This module provides the A2A server entry point for the orchestrator agent,
which routes alerts to specialized agents.

Supports both standard A2A and message/stream endpoint for SSE streaming.

Usage:
    python -m alerts.a2a.orchestrator_server --host 0.0.0.0 --port 10000

Note: The Insider Trading Agent server must be running before starting
the orchestrator server.
"""

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

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

from alerts.a2a.orchestrator_executor import OrchestratorAgentExecutor
from alerts.config import ConfigurationError, get_config, setup_logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global executor reference for streaming endpoint
_executor: OrchestratorAgentExecutor | None = None


async def message_stream_endpoint(request: Request):
    """Handle SSE streaming for A2A message/stream requests.

    This endpoint receives A2A message requests and streams progress events
    back to the client using Server-Sent Events. It proxies streaming events
    from specialized agents.

    Request body should be JSON-RPC 2.0 format:
    {
        "jsonrpc": "2.0",
        "method": "message/stream",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "textPart", "text": "path/to/alert.xml"}]
            }
        },
        "id": "request-id"
    }
    """
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

    # Generate task ID
    task_id = body.get("id", str(uuid.uuid4()))

    logger.info(f"Starting streaming orchestration for task {task_id}: {alert_path}")

    async def event_generator():
        """Generate SSE events from executor streaming."""
        try:
            async for event in _executor.execute_stream(task_id, alert_path):
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected for task {task_id}")
                    break

                # Extract event metadata
                metadata = event.get("result", {}).get("metadata", {})
                event_type = metadata.get("event_type", "update")
                event_id = metadata.get("event_id", str(uuid.uuid4()))

                # Yield event as SSE
                yield {
                    "data": json.dumps(event),
                    "event": event_type,
                    "id": event_id,
                    "retry": 5000,
                }

                # Check for final event
                if event.get("result", {}).get("taskStatusUpdateEvent", {}).get("final", False):
                    logger.info(f"Final event sent for task {task_id}")
                    break

                # Small delay to prevent overwhelming client
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
                        "taskStatusUpdateEvent": {
                            "task": {"id": task_id, "state": "failed"},
                            "final": True,
                        },
                    },
                }),
                "event": "error",
            }

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )


async def _error_generator(error_message: str):
    """Generate an error event."""
    yield {
        "data": json.dumps({
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": error_message,
            },
        }),
        "event": "error",
    }


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
        global _executor
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url=insider_trading_url,
            wash_trade_agent_url=wash_trade_url,
            data_dir=config.data.data_dir,
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

        logger.info(f"Server starting at http://{host}:{port}")
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
