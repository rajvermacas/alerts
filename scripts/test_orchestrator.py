#!/usr/bin/env python
"""Test script for the Orchestrator A2A server with Proactive Information Flow.

This script demonstrates how to send an AnalysisRequest to the orchestrator
using the BigDataSimulator to construct the proper request with all tool data.

Usage:
    # Test with default insider trading alert
    python scripts/test_orchestrator.py

    # Test with a specific alert file
    python scripts/test_orchestrator.py --alert test_data/alerts/alert_genuine.xml

    # Test wash trade alert
    python scripts/test_orchestrator.py --alert test_data/alerts/wash_trade/wash_genuine.xml

    # Use streaming mode
    python scripts/test_orchestrator.py --streaming

    # Specify custom orchestrator URL
    python scripts/test_orchestrator.py --url http://localhost:10000
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

import click
import httpx

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alerts.mock.bigdata_simulator import BigDataSimulator
from alerts.models.request import AnalysisRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def send_analysis_request(
    orchestrator_url: str,
    request: AnalysisRequest,
    use_streaming: bool = False,
) -> dict:
    """Send an AnalysisRequest to the orchestrator.

    Args:
        orchestrator_url: URL of the orchestrator server
        request: AnalysisRequest with alert_xml, agent_type, and tool_data
        use_streaming: Whether to use SSE streaming

    Returns:
        Response from the orchestrator
    """
    endpoint = "/api/analyze"
    if use_streaming:
        endpoint = "/api/analyze/stream"

    url = f"{orchestrator_url}{endpoint}"
    logger.info(f"Sending request to: {url}")
    logger.info(f"Agent type: {request.agent_type}")
    logger.info(f"Tool data keys: {list(request.tool_data.keys())}")

    async with httpx.AsyncClient(timeout=300.0) as client:
        if use_streaming:
            # SSE streaming
            logger.info("Using SSE streaming mode...")
            async with client.stream(
                "POST",
                url,
                json=request.model_dump(mode="json"),
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                event = json.loads(data)
                                event_type = event.get("event_type", "unknown")
                                print(f"[{event_type}] {json.dumps(event, indent=2)}")
                            except json.JSONDecodeError:
                                print(f"[raw] {data}")

                return {"status": "streaming_complete"}
        else:
            # Regular POST request
            response = await client.post(
                url,
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            return response.json()


def print_request_summary(request: AnalysisRequest) -> None:
    """Print a summary of the AnalysisRequest."""
    print("\n" + "=" * 70)
    print("ANALYSIS REQUEST SUMMARY")
    print("=" * 70)
    print(f"Agent Type: {request.agent_type}")
    print(f"Alert XML Length: {len(request.alert_xml)} characters")
    print("\nTool Data:")
    for tool_name, tool_input in request.tool_data.items():
        data_preview = tool_input.data[:100].replace("\n", " ")
        if len(tool_input.data) > 100:
            data_preview += "..."
        print(f"  - {tool_name} ({tool_input.format}): {data_preview}")
    print("=" * 70 + "\n")


def print_response(response: dict) -> None:
    """Print the response from the orchestrator."""
    print("\n" + "=" * 70)
    print("ORCHESTRATOR RESPONSE")
    print("=" * 70)

    if "determination" in response:
        print(f"Determination: {response.get('determination')}")
        print(f"Confidence: {response.get('genuine_alert_confidence')}%")
        print(f"Alert ID: {response.get('alert_id')}")
        print(f"Alert Type: {response.get('alert_type')}")

        if response.get("key_findings"):
            print("\nKey Findings:")
            for finding in response.get("key_findings", []):
                print(f"  - {finding}")

        if response.get("reasoning_narrative"):
            print(f"\nReasoning:\n{response.get('reasoning_narrative')[:500]}...")

        print(f"\nRecommended Action: {response.get('recommended_action')}")
    else:
        print(json.dumps(response, indent=2))

    print("=" * 70 + "\n")


@click.command()
@click.option(
    "--url",
    default="http://localhost:10000",
    help="Orchestrator server URL",
)
@click.option(
    "--alert",
    default="test_data/alerts/alert_genuine.xml",
    help="Path to alert XML file",
)
@click.option(
    "--streaming",
    is_flag=True,
    help="Use SSE streaming mode",
)
@click.option(
    "--data-dir",
    default="test_data",
    help="Path to test data directory",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output",
)
def main(url: str, alert: str, streaming: bool, data_dir: str, verbose: bool):
    """Test the Orchestrator with Proactive Information Flow.

    This script uses BigDataSimulator to construct an AnalysisRequest
    with all required tool data, then sends it to the orchestrator.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate paths
    alert_path = Path(alert)
    if not alert_path.exists():
        logger.error(f"Alert file not found: {alert_path}")
        sys.exit(1)

    data_path = Path(data_dir)
    if not data_path.exists():
        logger.error(f"Data directory not found: {data_path}")
        sys.exit(1)

    logger.info(f"Loading alert from: {alert_path}")
    logger.info(f"Using data directory: {data_path}")

    # Use BigDataSimulator to construct the request
    try:
        simulator = BigDataSimulator(str(data_path))
        request = simulator.create_request(str(alert_path))
        logger.info(f"Created AnalysisRequest for agent type: {request.agent_type}")
    except FileNotFoundError as e:
        logger.error(f"Failed to create request: {e}")
        sys.exit(1)

    # Print request summary
    print_request_summary(request)

    # Send to orchestrator
    try:
        response = asyncio.run(send_analysis_request(url, request, streaming))
        if not streaming:
            print_response(response)
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        sys.exit(1)
    except httpx.ConnectError:
        logger.error(f"Failed to connect to orchestrator at {url}")
        logger.error("Make sure the orchestrator server is running:")
        logger.error("  python -m alerts.a2a.orchestrator_server --port 10000")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Request failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
