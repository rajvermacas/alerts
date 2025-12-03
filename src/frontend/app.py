"""FastAPI application for SMARTS Alert Analyzer frontend.

This module provides the web interface for uploading alert XML files
and viewing analysis results. It communicates with the orchestrator
agent via A2A protocol.
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
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
REPORTS_DIR = Path("resources/reports")
TEMP_DIR = Path(tempfile.gettempdir()) / "alerts_frontend"

# Ensure directories exist
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> JSONResponse:
    """Accept XML file upload and start analysis.

    Args:
        background_tasks: FastAPI background tasks handler
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

    # Save file to temp directory
    temp_file_path = TEMP_DIR / f"{task_id}.xml"
    try:
        content = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(content)
        logger.info(f"Saved uploaded file to: {temp_file_path}")
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to save uploaded file",
        )

    # Create task
    task_manager.create_task(task_id)

    # Start background analysis
    background_tasks.add_task(
        run_analysis,
        task_id=task_id,
        file_path=temp_file_path,
    )

    return JSONResponse({"task_id": task_id})


async def run_analysis(task_id: str, file_path: Path) -> None:
    """Run alert analysis in background.

    This function sends the alert to the orchestrator via A2A protocol
    and updates the task status when complete.

    Args:
        task_id: ID of the task to update
        file_path: Path to the uploaded XML file
    """
    logger.info(f"Starting analysis for task {task_id}")

    try:
        # Send to orchestrator via A2A
        result = await send_to_orchestrator(str(file_path))

        if result.get("status") == "error":
            logger.error(f"Analysis failed: {result.get('error')}")
            task_manager.update_task(
                task_id=task_id,
                status="error",
                error=result.get("error", "Unknown error"),
            )
            return

        # Extract decision from response
        response = result.get("response", {})
        decision = extract_decision_from_response(response)

        if decision is None:
            logger.error("Failed to extract decision from response")
            task_manager.update_task(
                task_id=task_id,
                status="error",
                error="Failed to extract decision from agent response",
            )
            return

        # Determine alert type from decision
        alert_type = decision.get("alert_type", "unknown").lower()
        alert_id = decision.get("alert_id", task_id[:8])

        # Update task with success
        task_manager.update_task(
            task_id=task_id,
            status="complete",
            alert_id=alert_id,
            alert_type=alert_type,
            decision=decision,
        )
        logger.info(f"Analysis complete for task {task_id}: {alert_type}")

    except Exception as e:
        logger.error(f"Analysis error for task {task_id}: {e}")
        task_manager.update_task(
            task_id=task_id,
            status="error",
            error=str(e),
        )

    finally:
        # Cleanup temp file
        try:
            if file_path.exists():
                os.remove(file_path)
                logger.info(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file: {e}")


async def send_to_orchestrator(alert_path: str) -> Dict[str, Any]:
    """Send alert to orchestrator via A2A protocol.

    Args:
        alert_path: Path to the alert XML file

    Returns:
        Dictionary with response or error
    """
    logger.info(f"Sending alert to orchestrator: {alert_path}")

    async with httpx.AsyncClient(timeout=300.0) as httpx_client:
        # Get agent card
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=ORCHESTRATOR_URL,
        )

        try:
            agent_card = await resolver.get_agent_card()
            logger.info(f"Connected to orchestrator: {agent_card.name}")
        except Exception as e:
            logger.error(f"Failed to connect to orchestrator: {e}")
            return {
                "status": "error",
                "error": f"Analysis service unavailable. Please ensure servers are running. Error: {str(e)}",
            }

        # Create client
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        # Create message
        message_payload = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": f"Analyze the alert at: {alert_path}",
                    }
                ],
                "messageId": uuid4().hex,
            },
        }

        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**message_payload),
        )

        try:
            response = await client.send_message(request)
            response_data = response.model_dump(mode="json", exclude_none=True)
            logger.info("Received response from orchestrator")
            return {
                "status": "success",
                "response": response_data,
            }
        except Exception as e:
            logger.error(f"Failed to communicate with orchestrator: {e}")
            return {
                "status": "error",
                "error": f"Analysis timed out or failed. Please try again. Error: {str(e)}",
            }


def extract_decision_from_response(response: Dict[str, Any]) -> Dict[str, Any] | None:
    """Extract decision JSON from A2A response using DataPart artifacts.

    This function extracts structured JSON data from DataPart artifacts.
    Fail-fast: If DataPart extraction fails, return None immediately.

    Args:
        response: Raw A2A response dictionary

    Returns:
        Decision dictionary or None if not found

    Raises:
        ValueError: If response structure is invalid
    """
    logger.info("=" * 60)
    logger.info("EXTRACTING DECISION FROM RESPONSE (DataPart only)")
    logger.info("=" * 60)
    logger.info(f"Response keys: {response.keys() if response else 'None'}")

    # Save full response to debug file
    debug_dir = Path("resources/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / f"a2a_response_{uuid4().hex[:8]}.json"
    try:
        with open(debug_file, "w") as f:
            json.dump(response, f, indent=2)
        logger.info(f"Full response saved to: {debug_file}")
    except Exception as e:
        logger.warning(f"Failed to save debug response: {e}")

    # Extract from DataPart (fail-fast if not found)
    decision = _extract_from_datapart(response)
    if decision:
        logger.info("Successfully extracted decision from DataPart")
        return decision

    logger.error("Failed to extract decision from DataPart - no fallback, failing fast")
    return None


def _extract_from_datapart(response: Dict[str, Any]) -> Dict[str, Any] | None:
    """Extract decision from DataPart artifacts (new approach).

    Args:
        response: Raw A2A response dictionary

    Returns:
        Decision dictionary or None if not found
    """
    try:
        result = response.get("result", {})
        artifacts = result.get("artifacts", [])

        # Look for orchestrator_result_json artifact with DataPart
        for artifact in artifacts:
            if artifact.get("name") == "orchestrator_result_json":
                logger.info("Found orchestrator_result_json artifact")
                parts = artifact.get("parts", [])
                for part in parts:
                    if part.get("kind") == "data":
                        logger.info("Found DataPart in orchestrator_result_json")
                        # Direct access to structured JSON
                        data = part.get("data", {})

                        # Extract from nested agent response
                        nested_result = data.get("result", {})
                        nested_artifacts = nested_result.get("artifacts", [])
                        logger.info(f"Found {len(nested_artifacts)} nested artifacts")

                        # Look for *_decision_json artifact with DataPart
                        for nested_artifact in nested_artifacts:
                            artifact_name = nested_artifact.get("name", "")
                            logger.info(f"Checking nested artifact: {artifact_name}")
                            if artifact_name.endswith("_json"):
                                nested_parts = nested_artifact.get("parts", [])
                                for nested_part in nested_parts:
                                    if nested_part.get("kind") == "data":
                                        decision = nested_part.get("data", {})
                                        if isinstance(decision, dict) and "determination" in decision:
                                            logger.info(f"Found determination in DataPart: {artifact_name}")
                                            return decision

        return None
    except Exception as e:
        logger.error(f"Error in DataPart extraction: {e}", exc_info=True)
        return None


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
    json_path = REPORTS_DIR / f"decision_{alert_id}.json"

    if json_path.exists():
        return FileResponse(
            path=json_path,
            media_type="application/json",
            filename=f"decision_{alert_id}.json",
        )

    # If not found, create temporary file from task decision
    temp_json_path = TEMP_DIR / f"decision_{task_id}.json"
    with open(temp_json_path, "w") as f:
        json.dump(task.decision, f, indent=2)

    return FileResponse(
        path=temp_json_path,
        media_type="application/json",
        filename=f"decision_{alert_id}.json",
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
    html_path = REPORTS_DIR / f"decision_{alert_id}.html"

    if html_path.exists():
        return FileResponse(
            path=html_path,
            media_type="text/html",
            filename=f"decision_{alert_id}.html",
        )

    raise HTTPException(
        status_code=404,
        detail="HTML report not found. The report may not have been generated.",
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
