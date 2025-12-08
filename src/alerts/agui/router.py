"""AG-UI Protocol FastAPI Router.

This module provides FastAPI endpoints for AG-UI protocol streaming using
the official AG-UI SDK (ag_ui.core, ag_ui.encoder).

Endpoints:
- POST /agui/run: Start a new analysis run with AG-UI event streaming
- POST /agui/awp: CopilotKit-compatible endpoint using RunAgentInput
- GET /agui/info: Get AG-UI endpoint information

The AG-UI protocol enables real-time bidirectional communication between
AI agents and frontend applications using Server-Sent Events (SSE).
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

# Import from official AG-UI SDK
from ag_ui.core import (
    RunAgentInput,
    EventType,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    CustomEvent,
)
from ag_ui.encoder import EventEncoder

from alerts.agui.adapter import AGUIAdapter

logger = logging.getLogger(__name__)

# Configuration
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:10000")
TEMP_DIR = Path(tempfile.gettempdir()) / "alerts_agui"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Create router
router = APIRouter(prefix="/agui", tags=["AG-UI Protocol"])


@router.post("/run")
async def start_agui_run(
    request: Request,
    file: UploadFile = File(...),
    thread_id: Optional[str] = Query(default=None),
) -> StreamingResponse:
    """Start a new AG-UI analysis run with file upload.

    This endpoint accepts an XML alert file and streams AG-UI events
    as the analysis progresses using the official AG-UI SDK.

    Args:
        request: FastAPI request
        file: Alert XML file to analyze
        thread_id: Optional thread ID for conversation context

    Returns:
        StreamingResponse with AG-UI event stream (text/event-stream)
    """
    logger.info(f"Starting AG-UI run with file: {file.filename}")

    # Validate file
    if not file.filename or not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Please upload an XML file")

    # Generate run ID
    run_id = str(uuid4())
    thread_id = thread_id or str(uuid4())

    # Save file
    temp_file_path = TEMP_DIR / f"{run_id}.xml"
    try:
        content = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(content)
        logger.info(f"Saved file to: {temp_file_path}")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Get accept header for encoder
    accept_header = request.headers.get("accept", "text/event-stream")

    return StreamingResponse(
        _agui_event_generator(run_id, thread_id, temp_file_path, request, accept_header),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/awp")
async def agui_awp_endpoint(
    request: Request,
    input_data: RunAgentInput,
) -> StreamingResponse:
    """AG-UI Agent Worker Protocol endpoint.

    This endpoint follows the AG-UI AWP standard, accepting RunAgentInput
    and streaming BaseEvent objects. Compatible with CopilotKit's HttpAgent.

    The input messages should contain the alert file path.

    Args:
        request: FastAPI request
        input_data: AG-UI RunAgentInput with messages, tools, and context

    Returns:
        StreamingResponse with AG-UI event stream
    """
    logger.info(f"AG-UI AWP request: thread_id={input_data.thread_id}, run_id={input_data.run_id}")

    # Extract alert path from messages
    alert_path = None
    for msg in input_data.messages:
        if hasattr(msg, 'content'):
            content = msg.content
            if isinstance(content, str) and content.endswith(".xml"):
                if Path(content).exists():
                    alert_path = Path(content)
                    break

    if not alert_path:
        raise HTTPException(
            status_code=400,
            detail="Messages must contain a valid path to an XML alert file",
        )

    # Use provided IDs or generate new ones
    run_id = input_data.run_id or str(uuid4())
    thread_id = input_data.thread_id or str(uuid4())

    # Get accept header for encoder
    accept_header = request.headers.get("accept", "text/event-stream")

    return StreamingResponse(
        _agui_event_generator(run_id, thread_id, alert_path, request, accept_header),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/info")
async def agui_info() -> JSONResponse:
    """Get AG-UI endpoint information.

    Returns information about the AG-UI implementation
    for frontend discovery and configuration.
    """
    return JSONResponse({
        "protocol": "AG-UI",
        "version": "1.0.0",
        "sdk": "ag-ui-protocol",
        "capabilities": {
            "streaming": True,
            "tools": True,
            "state_sync": True,
            "messages": True,
        },
        "endpoints": {
            "run": "/agui/run",
            "awp": "/agui/awp",
            "info": "/agui/info",
        },
        "events": [
            "RUN_STARTED",
            "RUN_FINISHED",
            "RUN_ERROR",
            "STEP_STARTED",
            "STEP_FINISHED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "TOOL_CALL_START",
            "TOOL_CALL_END",
            "STATE_SNAPSHOT",
            "STATE_DELTA",
            "CUSTOM",
        ],
    })


async def _agui_event_generator(
    run_id: str,
    thread_id: str,
    alert_path: Path,
    request: Request,
    accept_header: str = "text/event-stream",
):
    """Generate AG-UI events by proxying from orchestrator.

    This function connects to the orchestrator's A2A streaming endpoint,
    converts the A2A events to AG-UI format using the adapter, and yields
    them properly encoded using the official AG-UI EventEncoder.

    Args:
        run_id: Unique run identifier
        thread_id: Thread/conversation identifier
        alert_path: Path to alert XML file
        request: FastAPI request for disconnect checking
        accept_header: Accept header for EventEncoder

    Yields:
        SSE-formatted AG-UI events
    """
    adapter = AGUIAdapter(run_id=run_id, thread_id=thread_id)
    encoder = EventEncoder(accept=accept_header)
    event_count = 0
    last_keepalive = asyncio.get_event_loop().time()
    keepalive_interval = 25  # seconds

    try:
        # Connect to orchestrator
        async with httpx.AsyncClient(timeout=600.0) as client:
            stream_request = {
                "jsonrpc": "2.0",
                "method": "message/stream",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "textPart", "text": str(alert_path)}],
                    }
                },
                "id": run_id,
            }

            logger.info(f"Connecting to orchestrator: {ORCHESTRATOR_URL}/message/stream")

            async with client.stream(
                "POST",
                f"{ORCHESTRATOR_URL}/message/stream",
                json=stream_request,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code != 200:
                    logger.error(f"Orchestrator returned: {response.status_code}")
                    error_event = RunErrorEvent(
                        type=EventType.RUN_ERROR,
                        message=f"Orchestrator returned status {response.status_code}",
                    )
                    yield encoder.encode(error_event)
                    return

                # Process A2A events and convert to AG-UI
                async for line in response.aiter_lines():
                    # Check for client disconnect
                    if await request.is_disconnected():
                        logger.info(f"Client disconnected for run {run_id}")
                        break

                    # Keep-alive check
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_keepalive > keepalive_interval:
                        keep_alive = CustomEvent(
                            type=EventType.CUSTOM,
                            name="keep_alive",
                            value={"message": "Processing..."},
                        )
                        yield encoder.encode(keep_alive)
                        last_keepalive = current_time

                    # Parse SSE line
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str:
                            try:
                                a2a_event = json.loads(data_str)
                                event_count += 1

                                # Convert to AG-UI events using adapter
                                agui_events = adapter.convert_event(a2a_event)

                                # Encode and yield each event
                                for agui_event in agui_events:
                                    yield encoder.encode(agui_event)

                                # Check for final event
                                if a2a_event.get("result", {}).get("taskStatusUpdateEvent", {}).get("final", False):
                                    logger.info(f"Final event received for run {run_id}")
                                    break

                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON: {data_str[:100]}")

    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to orchestrator: {e}")
        error_event = RunErrorEvent(
            type=EventType.RUN_ERROR,
            message="Analysis service unavailable. Please ensure servers are running.",
        )
        yield encoder.encode(error_event)

    except asyncio.CancelledError:
        logger.info(f"Stream cancelled for run {run_id}")

    except Exception as e:
        logger.error(f"Stream error for run {run_id}: {e}", exc_info=True)
        error_event = RunErrorEvent(
            type=EventType.RUN_ERROR,
            message=f"Stream error: {str(e)}",
        )
        yield encoder.encode(error_event)

    finally:
        logger.info(f"Stream ended for run {run_id}, {event_count} A2A events processed")

        # Cleanup temp file if it exists
        temp_path = TEMP_DIR / f"{run_id}.xml"
        if temp_path.exists():
            try:
                temp_path.unlink()
                logger.debug(f"Cleaned up temp file: {temp_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup: {e}")
