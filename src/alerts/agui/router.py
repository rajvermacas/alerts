"""AG-UI Protocol FastAPI Router.

This module provides FastAPI endpoints for AG-UI protocol streaming,
enabling integration with CopilotKit and other AG-UI compatible frontends.

Endpoints:
- POST /agui/run: Start a new analysis run with AG-UI event streaming
- GET /agui/stream/{run_id}: Stream AG-UI events for an existing run
- POST /agui/message: CopilotKit-compatible message endpoint

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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from alerts.agui.adapter import AGUIAdapter
from alerts.agui.events import (
    AGUIEvent,
    CustomEvent,
    RunErrorEvent,
    RunStartedEvent,
)

logger = logging.getLogger(__name__)

# Configuration
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:10000")
TEMP_DIR = Path(tempfile.gettempdir()) / "alerts_agui"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Create router
router = APIRouter(prefix="/agui", tags=["AG-UI Protocol"])


class AGUIRunRequest(BaseModel):
    """Request to start a new AG-UI run."""

    thread_id: Optional[str] = Field(
        default=None, description="Thread/conversation ID for context"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class AGUIMessageRequest(BaseModel):
    """CopilotKit-compatible message request.

    This follows the AG-UI message/stream protocol format.
    """

    message: Dict[str, Any] = Field(description="Message content with role and parts")
    thread_id: Optional[str] = Field(default=None, description="Thread ID")
    run_id: Optional[str] = Field(default=None, description="Existing run ID to continue")


class MessagePart(BaseModel):
    """A part of a message."""

    type: str = Field(description="Part type (textPart, etc.)")
    text: Optional[str] = Field(default=None, description="Text content")


class Message(BaseModel):
    """A message in the AG-UI format."""

    role: str = Field(description="Message role (user, assistant, system)")
    parts: list[MessagePart] = Field(description="Message content parts")


@router.post("/run")
async def start_agui_run(
    request: Request,
    file: UploadFile = File(...),
    thread_id: Optional[str] = Query(default=None),
) -> EventSourceResponse:
    """Start a new AG-UI analysis run with file upload.

    This endpoint accepts an XML alert file and streams AG-UI events
    as the analysis progresses.

    Args:
        request: FastAPI request
        file: Alert XML file to analyze
        thread_id: Optional thread ID for conversation context

    Returns:
        EventSourceResponse with AG-UI event stream
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

    return EventSourceResponse(
        _agui_event_generator(run_id, thread_id, temp_file_path, request),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/message/stream")
async def agui_message_stream(
    request: Request,
    body: AGUIMessageRequest,
) -> EventSourceResponse:
    """CopilotKit-compatible message streaming endpoint.

    This endpoint follows the AG-UI protocol for message streaming,
    compatible with CopilotKit's useCoAgent hook.

    The message should contain the alert file path or content.

    Args:
        request: FastAPI request
        body: AG-UI message request

    Returns:
        EventSourceResponse with AG-UI event stream
    """
    logger.info(f"AG-UI message stream request: thread_id={body.thread_id}")

    # Extract message content
    message = body.message
    role = message.get("role", "user")
    parts = message.get("parts", [])

    # Get text content from parts
    alert_path = None
    for part in parts:
        if part.get("type") == "textPart":
            text = part.get("text", "")
            # Check if it's a file path
            if text.endswith(".xml") and Path(text).exists():
                alert_path = Path(text)
                break

    if not alert_path:
        raise HTTPException(
            status_code=400,
            detail="Message must contain a valid path to an XML alert file",
        )

    # Generate run/thread IDs
    run_id = body.run_id or str(uuid4())
    thread_id = body.thread_id or str(uuid4())

    return EventSourceResponse(
        _agui_event_generator(run_id, thread_id, alert_path, request),
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
        "capabilities": {
            "streaming": True,
            "tools": True,
            "state_sync": True,
            "messages": True,
        },
        "endpoints": {
            "run": "/agui/run",
            "message_stream": "/agui/message/stream",
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
):
    """Generate AG-UI events by proxying from orchestrator.

    This function connects to the orchestrator's A2A streaming endpoint,
    converts the A2A events to AG-UI format, and yields them.

    Args:
        run_id: Unique run identifier
        thread_id: Thread/conversation identifier
        alert_path: Path to alert XML file
        request: FastAPI request for disconnect checking

    Yields:
        SSE-formatted AG-UI events
    """
    adapter = AGUIAdapter(run_id=run_id, thread_id=thread_id)
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
                        run_id=run_id,
                        thread_id=thread_id,
                        error=f"Orchestrator returned status {response.status_code}",
                    )
                    yield {
                        "data": error_event.to_sse_data(),
                        "event": "RUN_ERROR",
                    }
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
                            run_id=run_id,
                            thread_id=thread_id,
                            event_name="keep_alive",
                            data={"message": "Processing..."},
                        )
                        yield {
                            "data": keep_alive.to_sse_data(),
                            "event": "CUSTOM",
                        }
                        last_keepalive = current_time

                    # Parse SSE line
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str:
                            try:
                                a2a_event = json.loads(data_str)
                                event_count += 1

                                # Convert to AG-UI events
                                agui_events = adapter.convert_event(a2a_event)

                                for agui_event in agui_events:
                                    yield {
                                        "data": agui_event.to_sse_data(),
                                        "event": agui_event.type.value if hasattr(agui_event.type, 'value') else str(agui_event.type),
                                        "id": str(uuid4()),
                                        "retry": 5000,
                                    }

                                # Check for final event
                                metadata = a2a_event.get("result", {}).get("metadata", {})
                                if a2a_event.get("result", {}).get("taskStatusUpdateEvent", {}).get("final", False):
                                    logger.info(f"Final event received for run {run_id}")
                                    break

                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON: {data_str[:100]}")

    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to orchestrator: {e}")
        error_event = RunErrorEvent(
            run_id=run_id,
            thread_id=thread_id,
            error="Analysis service unavailable. Please ensure servers are running.",
        )
        yield {
            "data": error_event.to_sse_data(),
            "event": "RUN_ERROR",
        }

    except asyncio.CancelledError:
        logger.info(f"Stream cancelled for run {run_id}")

    except Exception as e:
        logger.error(f"Stream error for run {run_id}: {e}", exc_info=True)
        error_event = RunErrorEvent(
            run_id=run_id,
            thread_id=thread_id,
            error=f"Stream error: {str(e)}",
        )
        yield {
            "data": error_event.to_sse_data(),
            "event": "RUN_ERROR",
        }

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
