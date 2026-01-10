"""A2A Server for the Insider Trading Alert Analyzer.

This module provides the A2A server entry point for the insider trading
alert analyzer, exposing it as an A2A-compatible agent.

Supports both standard A2A message/stream endpoint for SSE streaming.

Usage:
    python -m alerts.a2a.insider_trading_server --host 0.0.0.0 --port 10001
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

from pydantic import ValidationError
from starlette.responses import JSONResponse

from alerts.a2a.insider_trading_executor import InsiderTradingAgentExecutor
from alerts.config import ConfigurationError, get_config, setup_logging
from alerts.llm_factory import create_llm
from alerts.models.request import AnalysisRequest

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global executor reference for streaming endpoint
_executor: InsiderTradingAgentExecutor | None = None

# Keep-alive interval in seconds
KEEPALIVE_INTERVAL = 25


async def message_stream_endpoint(request: Request):
    """Handle SSE streaming for A2A message/stream requests.

    This endpoint receives A2A message requests and streams progress events
    back to the client using Server-Sent Events.

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
    task_id = str(uuid.uuid4())
    request_id = body.get("id", task_id)

    logger.info(f"Starting streaming analysis for task {task_id}: {alert_path}")

    async def event_generator():
        """Generate SSE events from executor streaming."""
        last_event_time = asyncio.get_event_loop().time()

        try:
            async for event in _executor.execute_stream(task_id, alert_path):
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected for task {task_id}")
                    break

                # Yield event as SSE
                yield {
                    "data": json.dumps(event),
                    "event": event.get("result", {}).get("metadata", {}).get("event_type", "update"),
                    "id": event.get("result", {}).get("metadata", {}).get("event_id", str(uuid.uuid4())),
                    "retry": 5000,
                }

                last_event_time = asyncio.get_event_loop().time()

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


async def api_analyze_stream_endpoint(request: Request):
    """Handle POST /api/analyze/stream for streaming proactive analysis.

    This endpoint accepts an AnalysisRequest JSON body and streams
    real-time progress events as the analysis progresses using SSE.

    Request body should be AnalysisRequest JSON:
    {
        "alert_xml": "<Alert>...</Alert>",
        "agent_type": "insider_trading",
        "tool_data": {
            "alert_reader": {"format": "xml", "data": "..."},
            "market_data": {"format": "csv", "data": "..."},
            ...
        }
    }

    Returns SSE stream with events:
        - analysis_started
        - tool_started
        - tool_completed
        - evaluation_started
        - analysis_complete
        - error (if failure)
    """
    global _executor

    if _executor is None:
        logger.error("Executor not initialized for streaming")
        return EventSourceResponse(
            _error_generator("Insider trading executor not initialized"),
            media_type="text/event-stream",
        )

    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON in streaming request: {e}")
        return EventSourceResponse(
            _error_generator(f"Invalid JSON: {e}"),
            media_type="text/event-stream",
        )

    # Validate request using Pydantic
    try:
        analysis_request = AnalysisRequest(**body)
    except ValidationError as e:
        logger.error(f"Request validation failed for streaming: {e}")
        return EventSourceResponse(
            _error_generator(f"Validation error: {e}"),
            media_type="text/event-stream",
        )

    task_id = str(uuid.uuid4())
    logger.info(f"Starting streaming analysis for task {task_id}")
    logger.info(f"Tool data keys: {list(analysis_request.tool_data.keys())}")

    async def event_generator():
        """Generate SSE events from agent streaming."""
        try:
            agent = _executor._get_agent()

            async for event in agent.astream_analyze_request(analysis_request, task_id):
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected for task {task_id}")
                    break

                # Convert StreamEvent to A2A format and yield as SSE
                a2a_event = event.to_a2a_format(
                    task_state="completed" if event.final else "working"
                )

                yield {
                    "data": json.dumps(a2a_event),
                    "event": event.event_type,
                    "id": event.event_id,
                    "retry": 5000,
                }

                if event.final:
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
                        "metadata": {
                            "event_type": "error",
                            "payload": {"message": str(e)},
                        },
                    },
                }),
                "event": "error",
            }

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )


async def api_analyze_endpoint(request: Request):
    """Handle POST /api/analyze for proactive information flow pattern.

    This endpoint accepts an AnalysisRequest JSON body and performs
    insider trading analysis using the pre-loaded tool data.

    Request body should be AnalysisRequest JSON:
    {
        "alert_xml": "<Alert>...</Alert>",
        "agent_type": "insider_trading",
        "tool_data": {
            "alert_reader": {"format": "xml", "data": "..."},
            "market_data": {"format": "csv", "data": "..."},
            ...
        }
    }

    Returns:
        200: InsiderTradingDecision JSON
        400: Validation error
        500: Internal server error
    """
    global _executor

    if _executor is None:
        logger.error("Executor not initialized")
        return JSONResponse(
            status_code=500,
            content={
                "error": "ANALYSIS_FAILED",
                "message": "Insider trading executor not initialized",
            },
        )

    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON in request: {e}")
        return JSONResponse(
            status_code=400,
            content={
                "error": "INVALID_REQUEST",
                "message": f"Invalid JSON: {str(e)}",
            },
        )

    # Validate request using Pydantic
    try:
        analysis_request = AnalysisRequest(**body)
    except ValidationError as e:
        logger.error(f"Request validation failed: {e}")
        return JSONResponse(
            status_code=400,
            content={
                "error": "MISSING_TOOL_DATA",
                "message": str(e),
                "details": str(e.errors()),
            },
        )

    logger.info(f"Received AnalysisRequest for insider trading analysis")
    logger.info(f"Tool data keys: {list(analysis_request.tool_data.keys())}")

    try:
        # Use the agent's analyze_request method
        agent = _executor._get_agent()
        decision = agent.analyze_request(analysis_request)

        # Return the decision as JSON
        return JSONResponse(
            status_code=200,
            content=decision.model_dump(mode="json", exclude_none=True),
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "ANALYSIS_FAILED",
                "message": f"Analysis failed: {str(e)}",
            },
        )


@click.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=10001, help="Port to bind to")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(host: str, port: int, verbose: bool) -> None:
    """Start the Insider Trading Alert Analyzer A2A server."""
    try:
        # Load configuration
        config = get_config()

        # Setup logging
        if verbose:
            config.logging.level = "DEBUG"
        setup_logging(config.logging)

        logger.info("=" * 60)
        logger.info("Starting Insider Trading Alert Analyzer A2A Server")
        logger.info("=" * 60)

        # Create LLM
        llm = create_llm(config)

        # Define agent skill
        skill = AgentSkill(
            id="analyze_insider_trading_alert",
            name="Insider Trading Alert Analysis",
            description=(
                "Analyzes SMARTS surveillance alerts for potential insider trading. "
                "Uses a fully agentic LLM-based approach to gather evidence from "
                "trader history, market data, news, and peer trades to make a "
                "determination (ESCALATE, CLOSE, or NEEDS_HUMAN_REVIEW)."
            ),
            tags=["insider trading", "compliance", "alert analysis", "surveillance"],
            examples=[
                "Analyze the alert at test_data/alerts/alert_genuine.xml",
                "Check this alert for insider trading: test_data/alerts/alert_false_positive.xml",
                "Review alert_ambiguous.xml for compliance concerns",
            ],
        )

        # Define agent card
        agent_card = AgentCard(
            name="Insider Trading Alert Analyzer",
            description=(
                "An intelligent compliance filter that analyzes SMARTS surveillance "
                "alerts for potential insider trading. Uses a fully agentic LLM-based "
                "approach with LangGraph, where each tool calls an LLM internally to "
                "interpret data rather than returning raw data."
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
        executor = InsiderTradingAgentExecutor(
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

        # Add the streaming endpoint (legacy file-based)
        app.routes.append(
            Route("/message/stream", message_stream_endpoint, methods=["POST"])
        )
        # Add the analyze endpoint for proactive information flow (non-streaming)
        app.routes.append(
            Route("/api/analyze", api_analyze_endpoint, methods=["POST"])
        )
        # Add the streaming analyze endpoint for proactive information flow (SSE)
        app.routes.append(
            Route("/api/analyze/stream", api_analyze_stream_endpoint, methods=["POST"])
        )

        logger.info(f"Server starting at http://{host}:{port}")
        logger.info(f"Agent card available at http://{host}:{port}/.well-known/agent.json")
        logger.info(f"Streaming endpoint: POST http://{host}:{port}/message/stream")
        logger.info(f"Analyze endpoint: POST http://{host}:{port}/api/analyze")
        logger.info(f"Analyze stream endpoint: POST http://{host}:{port}/api/analyze/stream")

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
