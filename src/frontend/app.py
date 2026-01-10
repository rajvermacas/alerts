"""FastAPI application for SMARTS Alert Analyzer frontend.

This module provides the web interface for uploading alert XML files
and viewing analysis results. It communicates with the orchestrator
agent via A2A protocol.

Supports real-time streaming via SSE for progress updates.
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

import click
import httpx
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette import EventSourceResponse

from alerts.mock.bigdata_simulator import BigDataSimulator
from frontend.task_manager import TaskManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Configuration
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:10000")

# Find project root (contains pyproject.toml or src directory)
# Navigate up from frontend module: src/frontend/app.py -> src/frontend -> src -> project_root
PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "resources" / "reports"
TEMP_DIR = Path(tempfile.gettempdir()) / "alerts_frontend"
DATA_DIR = PROJECT_ROOT / "test_data"

# Ensure directories exist
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Initialize BigDataSimulator for proactive info flow pattern
_bigdata_simulator: BigDataSimulator | None = None


def get_bigdata_simulator() -> BigDataSimulator:
    """Get or create the BigDataSimulator instance."""
    global _bigdata_simulator
    if _bigdata_simulator is None:
        _bigdata_simulator = BigDataSimulator(str(DATA_DIR))
    return _bigdata_simulator

# Initialize FastAPI app
app = FastAPI(
    title="SMARTS Alert Analyzer",
    description="Web interface for analyzing SMARTS surveillance alerts",
    version="0.1.0",
)

# Get the directory where this module is located
MODULE_DIR = Path(__file__).parent

# Mount static files
app.mount("/static", StaticFiles(directory=MODULE_DIR / "static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory=MODULE_DIR / "templates")

# Initialize task manager
task_manager = TaskManager(max_age_hours=1)


@app.get("/")
async def index(request: Request):
    """Serve the upload page.

    Args:
        request: FastAPI request object

    Returns:
        Rendered upload.html template
    """
    logger.info("Serving upload page")
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
) -> JSONResponse:
    """Accept XML file upload and create task for streaming analysis.

    This endpoint saves the file, creates an AnalysisRequest using the
    BigDataSimulator, and stores both for the SSE streaming endpoint.

    Uses the proactive information flow pattern where data is pre-loaded
    rather than loaded by individual tools.

    Args:
        file: Uploaded XML file

    Returns:
        JSON response with task_id

    Raises:
        HTTPException: If file is not XML or upload fails
    """
    logger.info(f"Received file upload: {file.filename}")

    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".xml"):
        logger.warning(f"Invalid file type: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="Please upload an XML file",
        )

    # Generate task ID
    task_id = uuid4().hex
    logger.info(f"Generated task_id: {task_id}")

    # Read file content
    try:
        content = await file.read()
        xml_content = content.decode("utf-8")
        logger.info(f"Read {len(xml_content)} bytes from uploaded file")
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to read uploaded file",
        )

    # Create AnalysisRequest using BigDataSimulator
    try:
        simulator = get_bigdata_simulator()
        analysis_request = simulator.create_request_from_content(xml_content)
        logger.info(
            f"Created AnalysisRequest for agent_type: {analysis_request.agent_type}, "
            f"tool_data keys: {list(analysis_request.tool_data.keys())}"
        )
    except Exception as e:
        logger.error(f"Failed to create AnalysisRequest: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to prepare analysis request: {str(e)}",
        )

    # Save the AnalysisRequest JSON for the streaming endpoint
    request_file_path = TEMP_DIR / f"{task_id}_request.json"
    try:
        with open(request_file_path, "w", encoding="utf-8") as f:
            f.write(analysis_request.model_dump_json())
        logger.info(f"Saved AnalysisRequest to: {request_file_path}")
    except Exception as e:
        logger.error(f"Failed to save AnalysisRequest: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to save analysis request",
        )

    # Create task (status: processing)
    # Analysis will be triggered by SSE streaming endpoint
    task_manager.create_task(task_id)
    logger.info(f"Task {task_id} created with agent_type: {analysis_request.agent_type}")

    return JSONResponse({
        "task_id": task_id,
        "agent_type": analysis_request.agent_type,
    })


@app.get("/api/status/{task_id}")
async def get_status(task_id: str) -> JSONResponse:
    """Get status of an analysis task.

    Args:
        task_id: ID of the task to check

    Returns:
        JSON response with task status

    Raises:
        HTTPException: If task not found
    """
    logger.debug(f"Status check for task: {task_id}")

    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == "processing":
        return JSONResponse({"status": "processing"})

    elif task.status == "error":
        return JSONResponse({
            "status": "error",
            "message": task.error or "Unknown error",
        })

    elif task.status == "complete":
        return JSONResponse({
            "status": "complete",
            "alert_type": task.alert_type,
            "alert_id": task.alert_id,
            "decision": task.decision,
        })

    return JSONResponse({"status": task.status})


@app.get("/api/stream/{task_id}")
async def stream_events(task_id: str, request: Request):
    """Stream real-time progress events for a task via SSE.

    This endpoint connects to the orchestrator's streaming endpoint
    and forwards events to the browser using Server-Sent Events.

    Uses the proactive information flow pattern by sending the
    AnalysisRequest to the orchestrator.

    Args:
        task_id: ID of the task to stream
        request: FastAPI request object

    Returns:
        EventSourceResponse with streaming events
    """
    logger.info(f"Starting SSE stream for task: {task_id}")

    task = task_manager.get_task(task_id)
    if task is None:
        return EventSourceResponse(
            _stream_error("Task not found"),
            media_type="text/event-stream",
        )

    # Get the AnalysisRequest JSON for this task
    request_file_path = TEMP_DIR / f"{task_id}_request.json"
    if not request_file_path.exists():
        # Fall back to legacy file path for backward compatibility
        temp_file_path = TEMP_DIR / f"{task_id}.xml"
        if not temp_file_path.exists():
            return EventSourceResponse(
                _stream_error("Analysis request not found"),
                media_type="text/event-stream",
            )
        # Use legacy streaming if only XML file exists
        return EventSourceResponse(
            _legacy_event_generator(task_id, temp_file_path, request),
            media_type="text/event-stream",
        )

    async def event_generator():
        """Generate SSE events by proxying from orchestrator's streaming endpoint.

        This uses the new /api/analyze/stream endpoint for real-time progress updates,
        implementing true SSE streaming instead of fake simulated events.
        """
        event_count = 0
        last_keepalive = asyncio.get_event_loop().time()
        keepalive_interval = 25  # seconds

        try:
            # Load AnalysisRequest from file
            with open(request_file_path, "r", encoding="utf-8") as f:
                analysis_request = json.load(f)

            logger.info(
                f"Loaded AnalysisRequest for task {task_id}, "
                f"agent_type: {analysis_request.get('agent_type')}"
            )

            # Connect to orchestrator's streaming endpoint for real-time events
            stream_url = f"{ORCHESTRATOR_URL}/api/analyze/stream"
            async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
                logger.info(f"Connecting to orchestrator stream: {stream_url}")

                async with client.stream(
                    "POST",
                    stream_url,
                    json=analysis_request,
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    if response.status_code != 200:
                        logger.error(f"Orchestrator stream failed: {response.status_code}")
                        yield {
                            "data": json.dumps({
                                "event_type": "error",
                                "message": f"Orchestrator returned status {response.status_code}",
                            }),
                            "event": "error",
                        }
                        return

                    # Parse and forward SSE events from orchestrator
                    async for line in response.aiter_lines():
                        # Check client disconnect
                        if await request.is_disconnected():
                            logger.info(f"Client disconnected for task {task_id}")
                            break

                        # Check for keepalive
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_keepalive > keepalive_interval:
                            yield {
                                "data": json.dumps({
                                    "event_type": "keep_alive",
                                    "message": "Processing...",
                                }),
                                "event": "keep_alive",
                            }
                            last_keepalive = current_time

                        # Parse SSE line
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str:
                                try:
                                    event_data = json.loads(data_str)
                                    event_count += 1

                                    # Extract event type from metadata
                                    metadata = event_data.get("result", {}).get("metadata", {})
                                    event_type = metadata.get("event_type", "update")
                                    event_id = metadata.get("event_id", str(uuid4()))

                                    # Forward the event to browser
                                    yield {
                                        "data": data_str,
                                        "event": event_type,
                                        "id": event_id,
                                        "retry": 5000,
                                    }

                                    # Check for final event and update task
                                    task_status = event_data.get("result", {}).get("taskStatusUpdateEvent", {})
                                    if task_status.get("final", False):
                                        logger.info(f"Final event received for task {task_id}")

                                        # Extract decision from final event and update task
                                        await _handle_streaming_final_event(
                                            task_id, event_data, analysis_request.get("agent_type")
                                        )
                                        break

                                except json.JSONDecodeError:
                                    logger.warning(f"Invalid JSON in SSE line: {data_str[:100]}")

        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to orchestrator: {e}")
            yield {
                "data": json.dumps({
                    "event_type": "error",
                    "message": "Analysis service unavailable. Please ensure servers are running.",
                }),
                "event": "error",
            }

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for task {task_id}")

        except Exception as e:
            logger.error(f"Stream error for task {task_id}: {e}", exc_info=True)
            yield {
                "data": json.dumps({
                    "event_type": "error",
                    "message": f"Stream error: {str(e)}",
                }),
                "event": "error",
            }

        finally:
            logger.info(f"Stream ended for task {task_id}, {event_count} events sent")
            # Cleanup request file
            if request_file_path.exists():
                try:
                    os.remove(request_file_path)
                    logger.info(f"Cleaned up request file: {request_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup request file: {e}")

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )


async def _legacy_event_generator(task_id: str, temp_file_path: Path, request: Request):
    """Legacy event generator for backward compatibility with file-based approach.

    This generator streams events from the orchestrator's /message/stream endpoint
    using the legacy file-path approach. It yields SSE events directly.

    Args:
        task_id: Task identifier
        temp_file_path: Path to the temporary alert XML file
        request: Starlette request for disconnect detection

    Yields:
        SSE event dictionaries with data, event type, and id
    """
    event_count = 0
    last_keepalive = asyncio.get_event_loop().time()
    keepalive_interval = 25  # seconds

    try:
        # Connect to orchestrator streaming endpoint
        async with httpx.AsyncClient(timeout=600.0) as client:
            # Build the streaming request
            stream_request = {
                "jsonrpc": "2.0",
                "method": "message/stream",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [
                            {"type": "textPart", "text": str(temp_file_path)}
                        ],
                    }
                },
                "id": task_id,
            }

            logger.info(f"[Legacy] Connecting to orchestrator stream: {ORCHESTRATOR_URL}/message/stream")

            async with client.stream(
                "POST",
                f"{ORCHESTRATOR_URL}/message/stream",
                json=stream_request,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code != 200:
                    logger.error(f"Orchestrator stream failed: {response.status_code}")
                    yield {
                        "data": json.dumps({
                            "event_type": "error",
                            "message": f"Orchestrator returned status {response.status_code}",
                        }),
                        "event": "error",
                    }
                    return

                # Process SSE stream from orchestrator
                async for line in response.aiter_lines():
                    # Check client disconnect
                    if await request.is_disconnected():
                        logger.info(f"Client disconnected for task {task_id}")
                        break

                    # Check for keepalive
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_keepalive > keepalive_interval:
                        yield {
                            "data": json.dumps({
                                "event_type": "keep_alive",
                                "message": "Processing...",
                            }),
                            "event": "keep_alive",
                        }
                        last_keepalive = current_time

                    # Parse SSE line
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str:
                            try:
                                event_data = json.loads(data_str)
                                event_count += 1

                                # Extract event type from metadata
                                metadata = event_data.get("result", {}).get("metadata", {})
                                event_type = metadata.get("event_type", "update")
                                event_id = metadata.get("event_id", str(uuid4()))

                                # Forward the event
                                yield {
                                    "data": data_str,
                                    "event": event_type,
                                    "id": event_id,
                                    "retry": 5000,
                                }

                                # Check for final event
                                task_status = event_data.get("result", {}).get("taskStatusUpdateEvent", {})
                                if task_status.get("final", False):
                                    logger.info(f"Final event received for task {task_id}")

                                    # Extract decision from final event and update task
                                    await _handle_final_event(task_id, event_data, temp_file_path)
                                    break

                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON in SSE line: {data_str[:100]}")

    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to orchestrator: {e}")
        yield {
            "data": json.dumps({
                "event_type": "error",
                "message": "Analysis service unavailable. Please ensure servers are running.",
            }),
            "event": "error",
        }

    except asyncio.CancelledError:
        logger.info(f"Stream cancelled for task {task_id}")

    except Exception as e:
        logger.error(f"Stream error for task {task_id}: {e}", exc_info=True)
        yield {
            "data": json.dumps({
                "event_type": "error",
                "message": f"Stream error: {str(e)}",
            }),
            "event": "error",
        }

    finally:
        logger.info(f"Stream ended for task {task_id}, {event_count} events sent")


async def _stream_error(message: str):
    """Generate an error event for streaming."""
    yield {
        "data": json.dumps({"event_type": "error", "message": message}),
        "event": "error",
    }


async def _handle_final_event(task_id: str, event_data: Dict, temp_file_path: Path) -> None:
    """Handle the final event and update task status.

    Extracts the complete decision from the streaming response and updates
    the task manager. Also handles temp file cleanup.

    Args:
        task_id: Task ID
        event_data: Final event data from SSE stream
        temp_file_path: Path to temp alert file
    """
    logger.info(f"Handling final event for task {task_id}")
    logger.info(f"Final event keys: {event_data.keys() if event_data else 'None'}")

    try:
        # Extract from nested A2A response structure
        result = event_data.get("result", {})
        metadata = result.get("metadata", {})
        payload = metadata.get("payload", {})

        logger.info(f"Payload keys: {payload.keys() if payload else 'None'}")

        # Extract full decision from payload - required field
        decision = payload.get("decision")

        if not decision:
            raise ValueError(f"Missing 'decision' in payload. Payload keys: {list(payload.keys())}")

        if "determination" not in decision:
            raise ValueError(f"Missing 'determination' in decision. Decision keys: {list(decision.keys())}")

        logger.info(f"Found full decision in payload: {decision.get('determination')}")

        # Extract alert info from decision - required fields
        alert_type = decision.get("alert_type")
        alert_id = decision.get("alert_id")

        if not alert_type:
            raise ValueError(f"Missing 'alert_type' in decision. Decision keys: {list(decision.keys())}")

        if not alert_id:
            raise ValueError(f"Missing 'alert_id' in decision. Decision keys: {list(decision.keys())}")

        logger.info(f"Extracted - alert_type: {alert_type}, alert_id: {alert_id}")
        logger.info(f"Decision determination: {decision['determination']}")

        # Update task with full decision
        task_manager.update_task(
            task_id=task_id,
            status="complete",
            alert_id=alert_id,
            alert_type=alert_type.lower(),
            decision=decision,
        )
        logger.info(f"Task {task_id} completed: {decision['determination']}")

    except Exception as e:
        logger.error(f"Error handling final event: {e}", exc_info=True)
        task_manager.update_task(
            task_id=task_id,
            status="error",
            error=f"Failed to process final event: {e}",
        )

    finally:
        # Cleanup temp file
        if temp_file_path.exists():
            try:
                os.remove(temp_file_path)
                logger.info(f"Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file: {e}")


async def _handle_streaming_final_event(
    task_id: str, event_data: Dict, agent_type: str | None
) -> None:
    """Handle the final event from streaming and update task status.

    Extracts the complete decision from the streaming response and updates
    the task manager. Used by the new /api/analyze/stream flow.

    Args:
        task_id: Task ID
        event_data: Final event data from SSE stream
        agent_type: Type of agent (insider_trading or wash_trade)
    """
    logger.info(f"Handling streaming final event for task {task_id}")
    logger.info(f"Final event keys: {event_data.keys() if event_data else 'None'}")

    try:
        # Extract from nested A2A response structure
        result = event_data.get("result", {})
        metadata = result.get("metadata", {})
        payload = metadata.get("payload", {})

        logger.info(f"Payload keys: {payload.keys() if payload else 'None'}")

        # Extract full decision from payload
        decision = payload.get("decision")

        if not decision:
            # Try alternative structure (direct decision in payload)
            decision = payload
            logger.info("Using payload as decision directly")

        if not decision or "determination" not in decision:
            logger.error(f"Missing decision in final event. Payload: {payload}")
            task_manager.update_task(
                task_id=task_id,
                status="error",
                error="Missing decision in final event",
            )
            return

        logger.info(f"Found decision: {decision.get('determination')}")

        # Extract alert info from decision
        alert_type_from_decision = decision.get("alert_type", agent_type or "unknown")
        alert_id = decision.get("alert_id", task_id[:8])

        logger.info(f"Extracted - alert_type: {alert_type_from_decision}, alert_id: {alert_id}")

        # Update task with full decision
        task_manager.update_task(
            task_id=task_id,
            status="complete",
            alert_id=alert_id,
            alert_type=alert_type_from_decision.lower() if alert_type_from_decision else "unknown",
            decision=decision,
        )
        logger.info(f"Task {task_id} completed: {decision['determination']}")

    except Exception as e:
        logger.error(f"Error handling streaming final event: {e}", exc_info=True)
        task_manager.update_task(
            task_id=task_id,
            status="error",
            error=f"Failed to process final event: {e}",
        )


@app.get("/api/download/{task_id}/json")
async def download_json(task_id: str) -> FileResponse:
    """Download decision JSON file.

    Args:
        task_id: ID of the task

    Returns:
        JSON file download

    Raises:
        HTTPException: If task not found or not complete
    """
    logger.info(f"JSON download request for task: {task_id}")

    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != "complete" or task.decision is None:
        raise HTTPException(status_code=400, detail="Analysis not complete")

    # Check if file exists in reports directory
    alert_id = task.alert_id or task_id[:8]

    # Determine file prefix based on alert type
    if task.alert_type == "wash_trade":
        file_prefix = "wash_trade_decision"
    else:
        file_prefix = "decision"

    json_path = REPORTS_DIR / f"{file_prefix}_{alert_id}.json"

    if json_path.exists():
        return FileResponse(
            path=json_path,
            media_type="application/json",
            filename=f"{file_prefix}_{alert_id}.json",
        )

    # If not found, create temporary file from task decision
    temp_json_path = TEMP_DIR / f"{file_prefix}_{task_id}.json"
    with open(temp_json_path, "w") as f:
        json.dump(task.decision, f, indent=2)

    return FileResponse(
        path=temp_json_path,
        media_type="application/json",
        filename=f"{file_prefix}_{alert_id}.json",
    )


@app.get("/api/download/{task_id}/html")
async def download_html(task_id: str) -> FileResponse:
    """Download generated HTML report.

    Args:
        task_id: ID of the task

    Returns:
        HTML file download

    Raises:
        HTTPException: If task not found or report not available
    """
    logger.info(f"HTML download request for task: {task_id}")

    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != "complete":
        raise HTTPException(status_code=400, detail="Analysis not complete")

    # Check if file exists in reports directory
    alert_id = task.alert_id or task_id[:8]

    # Determine file prefix based on alert type
    logger.info(f"HTML download - alert_type: '{task.alert_type}', alert_id: '{alert_id}'")
    if task.alert_type == "wash_trade":
        file_prefix = "wash_trade_decision"
    else:
        file_prefix = "decision"

    html_path = REPORTS_DIR / f"{file_prefix}_{alert_id}.html"
    logger.info(f"Looking for HTML file: {html_path} (exists: {html_path.exists()})")

    if html_path.exists():
        return FileResponse(
            path=html_path,
            media_type="text/html",
            filename=f"{file_prefix}_{alert_id}.html",
        )

    raise HTTPException(
        status_code=404,
        detail=f"HTML report not found at {html_path}. alert_type={task.alert_type}",
    )


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("=" * 60)
    logger.info("SMARTS Alert Analyzer Frontend Starting")
    logger.info("=" * 60)
    logger.info(f"Orchestrator URL: {ORCHESTRATOR_URL}")
    logger.info(f"Reports directory: {REPORTS_DIR}")
    logger.info(f"Temp directory: {TEMP_DIR}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("SMARTS Alert Analyzer Frontend Shutting Down")
    # Cleanup old tasks
    task_manager.cleanup_old_tasks()


@click.command()
@click.option(
    "--port",
    default=8080,
    help="Port to run the frontend server on",
)
@click.option(
    "--host",
    default="0.0.0.0",
    help="Host to bind the server to",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload for development",
)
@click.option(
    "--orchestrator-url",
    default="http://localhost:10000",
    help="URL of the orchestrator A2A server",
)
def main(port: int, host: str, reload: bool, orchestrator_url: str) -> None:
    """Start the SMARTS Alert Analyzer Frontend server."""
    global ORCHESTRATOR_URL
    ORCHESTRATOR_URL = orchestrator_url

    logger.info(f"Starting frontend server on {host}:{port}")
    logger.info(f"Orchestrator URL: {orchestrator_url}")

    uvicorn.run(
        "frontend.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
