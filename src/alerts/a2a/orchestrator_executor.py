"""A2A AgentExecutor for the Orchestrator Agent.

This module wraps the OrchestratorAgent as an A2A-compatible executor,
allowing it to receive alert analysis requests via the A2A protocol.

Supports both synchronous execute() and async execute_stream() for SSE streaming.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict

import httpx
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    InternalError,
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

from alerts.a2a.orchestrator import OrchestratorAgent

logger = logging.getLogger(__name__)


class OrchestratorAgentExecutor(AgentExecutor):
    """A2A AgentExecutor that wraps the OrchestratorAgent.

    This executor receives alert analysis requests via A2A protocol
    and routes them to specialized agents.
    """

    def __init__(
        self,
        insider_trading_agent_url: str = "http://localhost:10001",
        wash_trade_agent_url: str = "http://localhost:10002",
        data_dir: Path | None = None,
    ) -> None:
        """Initialize the executor.

        Args:
            insider_trading_agent_url: URL of the insider trading agent A2A server
            wash_trade_agent_url: URL of the wash trade agent A2A server
            data_dir: Path to data directory (optional)
        """
        self.orchestrator = OrchestratorAgent(
            insider_trading_agent_url=insider_trading_agent_url,
            wash_trade_agent_url=wash_trade_agent_url,
            data_dir=data_dir,
        )
        logger.info("OrchestratorAgentExecutor initialized")
        logger.info(f"Insider Trading Agent URL: {insider_trading_agent_url}")
        logger.info(f"Wash Trade Agent URL: {wash_trade_agent_url}")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute the orchestrator to route and analyze an alert.

        Args:
            context: Request context containing the message
            event_queue: Queue for sending events back to the client
        """
        logger.info("OrchestratorAgentExecutor.execute called")

        # Validate request
        if self._validate_request(context):
            raise ServerError(error=InvalidParamsError())

        # Get user input (alert file path)
        user_input = context.get_user_input()
        logger.info(f"Received request: {user_input}")

        # Create or get task
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            # Update status to working
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    "Reading alert to determine type...",
                    task.context_id,
                    task.id,
                ),
            )

            # Parse alert file path from input
            alert_path = self._extract_alert_path(user_input)
            if not alert_path:
                await updater.update_status(
                    TaskState.input_required,
                    new_agent_text_message(
                        "Please provide the path to the alert XML file to analyze.",
                        task.context_id,
                        task.id,
                    ),
                    final=True,
                )
                return

            # Verify file exists
            alert_file = Path(alert_path)
            if not alert_file.exists():
                # Try relative to data_dir
                if self.orchestrator.data_dir:
                    alert_file = self.orchestrator.data_dir / alert_path
                if not alert_file.exists():
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(
                            f"Alert file not found: {alert_path}. Please provide a valid path.",
                            task.context_id,
                            task.id,
                        ),
                        final=True,
                    )
                    return

            # Update status
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    f"Analyzing alert: {alert_file}",
                    task.context_id,
                    task.id,
                ),
            )

            # Route and analyze the alert
            result = await self.orchestrator.analyze_alert(alert_file)

            # Format result based on which agent handled the request
            routed_to = result.get("routed_to")
            if routed_to in ("insider_trading_agent", "wash_trade_agent"):
                if result.get("agent_response", {}).get("status") == "success":
                    response_text = self._format_success_response(result)
                else:
                    response_text = self._format_error_response(result)
            else:
                response_text = self._format_unsupported_response(result)

            # Add text artifact (for human readability)
            await updater.add_artifact(
                [Part(root=TextPart(text=response_text))],
                name="orchestrator_result_text",
            )

            # Add structured data artifact (for machine parsing)
            agent_response = result.get("agent_response", {})
            if agent_response.get("status") == "success":
                agent_response_data = agent_response.get("response", {})
                await updater.add_artifact(
                    [Part(root=DataPart(data=agent_response_data))],
                    name="orchestrator_result_json",
                )

            # Complete the task
            await updater.complete()
            logger.info("Orchestrator completed processing")

        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")
            await updater.update_status(
                TaskState.input_required,
                new_agent_text_message(
                    f"Error: {str(e)}. Please provide a valid alert file path.",
                    task.context_id,
                    task.id,
                ),
                final=True,
            )

        except Exception as e:
            logger.error(f"Orchestrator failed: {e}", exc_info=True)
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """Validate the incoming request.

        Args:
            context: Request context to validate

        Returns:
            True if request is invalid, False if valid
        """
        # Validate message structure
        if not context.message:
            logger.warning("Request missing message")
            return True  # Invalid

        # Validate message has parts
        if not hasattr(context.message, "parts") or not context.message.parts:
            logger.warning("Request message missing parts")
            return True  # Invalid

        # Validate has text content
        user_input = context.get_user_input()
        if not user_input or not user_input.strip():
            logger.warning("Request has empty user input")
            return True  # Invalid

        return False  # Valid

    def _extract_alert_path(self, user_input: str) -> str | None:
        """Extract alert file path from user input.

        Args:
            user_input: Raw user input string

        Returns:
            Alert file path or None if not found
        """
        if not user_input:
            return None

        # Check if input contains a file path
        input_lower = user_input.lower()

        # Look for common patterns
        if ".xml" in input_lower:
            words = user_input.split()
            for word in words:
                if ".xml" in word.lower():
                    path = word.strip("'\"")
                    return path

        # If the entire input looks like a path
        if "/" in user_input or user_input.endswith(".xml"):
            return user_input.strip()

        return user_input.strip() if user_input.strip() else None

    def _format_success_response(self, result: dict) -> str:
        """Format a successful response.

        Args:
            result: Result dictionary from orchestrator

        Returns:
            Formatted string
        """
        routed_to = result.get("routed_to", "unknown")
        agent_display_name = {
            "insider_trading_agent": "Insider Trading Agent",
            "wash_trade_agent": "Wash Trade Agent",
        }.get(routed_to, routed_to)

        lines = [
            "=" * 60,
            "ORCHESTRATOR RESULT",
            "=" * 60,
            "",
            f"Alert ID: {result.get('alert_id', 'Unknown')}",
            f"Alert Type: {result.get('alert_type', 'Unknown')}",
            f"Rule Violated: {result.get('rule_violated', 'Unknown')}",
            f"Category: {result.get('category', 'Unknown')}",
            f"Routed To: {agent_display_name}",
            "",
            "--- Agent Response ---",
        ]

        agent_response = result.get("agent_response", {})
        if "response" in agent_response:
            # Pretty print the response
            lines.append(json.dumps(agent_response["response"], indent=2))
        else:
            lines.append(str(agent_response))

        return "\n".join(lines)

    def _format_error_response(self, result: dict) -> str:
        """Format an error response.

        Args:
            result: Result dictionary from orchestrator

        Returns:
            Formatted string
        """
        routed_to = result.get("routed_to", "unknown")
        agent_display_name = {
            "insider_trading_agent": "Insider Trading Agent",
            "wash_trade_agent": "Wash Trade Agent",
        }.get(routed_to, routed_to)

        lines = [
            "=" * 60,
            "ORCHESTRATOR ERROR",
            "=" * 60,
            "",
            f"Alert ID: {result.get('alert_id', 'Unknown')}",
            f"Alert Type: {result.get('alert_type', 'Unknown')}",
            f"Category: {result.get('category', 'Unknown')}",
            f"Routed To: {agent_display_name}",
            "",
            "--- Error ---",
            result.get("agent_response", {}).get("error", "Unknown error"),
        ]
        return "\n".join(lines)

    def _format_unsupported_response(self, result: dict) -> str:
        """Format a response for unsupported alert types.

        Args:
            result: Result dictionary from orchestrator

        Returns:
            Formatted string
        """
        lines = [
            "=" * 60,
            "ORCHESTRATOR RESULT - UNSUPPORTED ALERT TYPE",
            "=" * 60,
            "",
            f"Alert ID: {result.get('alert_id', 'Unknown')}",
            f"Alert Type: {result.get('alert_type', 'Unknown')}",
            f"Rule Violated: {result.get('rule_violated', 'Unknown')}",
            "",
            result.get("message", "Alert type not supported"),
        ]
        return "\n".join(lines)

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Cancel the current execution.

        Args:
            context: Request context
            event_queue: Event queue

        Raises:
            ServerError: Cancellation is not supported
        """
        raise ServerError(error=UnsupportedOperationError())

    async def execute_stream(
        self,
        task_id: str,
        alert_path: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute analysis with streaming events, proxying from specialized agents.

        This method streams progress events as the analysis progresses,
        proxying events from the appropriate specialized agent.

        Args:
            task_id: Task ID for event correlation
            alert_path: Path to the alert XML file

        Yields:
            Dict containing A2A-formatted streaming events
        """
        logger.info(f"Starting streaming orchestration for task {task_id}: {alert_path}")

        # Resolve alert file path
        alert_file = Path(alert_path)
        if not alert_file.exists():
            if self.orchestrator.data_dir:
                alert_file = self.orchestrator.data_dir / alert_path
            if not alert_file.exists():
                yield self._create_error_event(
                    task_id,
                    f"Alert file not found: {alert_path}",
                    "initialization",
                )
                return

        # Send initial event
        yield self._create_status_event(
            task_id,
            "analysis_started",
            "Reading alert to determine type...",
            "working",
        )

        try:
            # Read and determine alert type
            alert_info = self.orchestrator.read_alert(alert_file)
            alert_type = alert_info.alert_type
            category = alert_info.category.value

            logger.info(f"Alert type: {alert_type}, Category: {category}")

            yield self._create_status_event(
                task_id,
                "routing",
                f"Alert type: {alert_type}. Routing to specialized agent...",
                "working",
                {"alert_type": alert_type, "category": category},
            )

            # Determine which agent to route to
            target_agent_url = None
            agent_name = None

            if alert_info.is_insider_trading:
                target_agent_url = self.orchestrator.insider_trading_agent_url
                agent_name = "insider_trading"
                logger.info(f"Routing to Insider Trading Agent: {target_agent_url}")
            elif alert_info.is_wash_trade:
                target_agent_url = self.orchestrator.wash_trade_agent_url
                agent_name = "wash_trade"
                logger.info(f"Routing to Wash Trade Agent: {target_agent_url}")
            else:
                logger.warning(f"Unsupported alert type: {alert_type}")
                yield self._create_error_event(
                    task_id,
                    f"Unsupported alert type: {alert_type}",
                    "routing",
                )
                return

            yield self._create_status_event(
                task_id,
                "agent_handoff",
                f"Handing off to {agent_name.replace('_', ' ').title()} Agent...",
                "working",
                {"agent": agent_name},
            )

            # Stream events from the specialized agent
            async for event in self._stream_from_agent(
                task_id,
                str(alert_file),
                target_agent_url,
                agent_name,
            ):
                yield event

        except FileNotFoundError as e:
            logger.error(f"File not found during streaming: {e}")
            yield self._create_error_event(task_id, str(e), "analysis")

        except Exception as e:
            logger.error(f"Streaming orchestration failed: {e}", exc_info=True)
            yield self._create_error_event(task_id, f"Orchestration failed: {str(e)}", "analysis")

    async def _stream_from_agent(
        self,
        task_id: str,
        alert_path: str,
        agent_url: str,
        agent_name: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream events from a specialized agent.

        Args:
            task_id: Task ID for correlation
            alert_path: Path to the alert file
            agent_url: URL of the specialized agent
            agent_name: Name of the agent for logging

        Yields:
            A2A-formatted events
        """
        stream_url = f"{agent_url}/message/stream"
        logger.info(f"Connecting to agent stream: {stream_url}")

        stream_request = {
            "jsonrpc": "2.0",
            "method": "message/stream",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "textPart", "text": alert_path}],
                }
            },
            "id": task_id,
        }

        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    stream_url,
                    json=stream_request,
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    if response.status_code != 200:
                        logger.error(f"Agent stream failed: {response.status_code}")
                        yield self._create_error_event(
                            task_id,
                            f"Agent returned status {response.status_code}",
                            "agent_connection",
                        )
                        return

                    # Parse and forward SSE events
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str:
                                try:
                                    event_data = json.loads(data_str)

                                    # Add orchestrator context to metadata
                                    if "result" in event_data and "metadata" in event_data.get("result", {}):
                                        event_data["result"]["metadata"]["orchestrated"] = True
                                        event_data["result"]["metadata"]["source_agent"] = agent_name

                                    yield event_data

                                    # Check for final event
                                    task_status = event_data.get("result", {}).get("taskStatusUpdateEvent", {})
                                    if task_status.get("final", False):
                                        logger.info(f"Final event received from {agent_name}")
                                        return

                                except json.JSONDecodeError as e:
                                    logger.warning(f"Invalid JSON in agent SSE: {e}")

        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to agent at {agent_url}: {e}")
            yield self._create_error_event(
                task_id,
                f"Failed to connect to {agent_name.replace('_', ' ')} agent. Ensure it is running.",
                "agent_connection",
            )

        except Exception as e:
            logger.error(f"Error streaming from agent: {e}", exc_info=True)
            yield self._create_error_event(task_id, f"Agent streaming error: {str(e)}", "agent_streaming")

    def _create_status_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        task_state: str,
        extra_payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Create a status update event.

        Args:
            task_id: Task ID
            event_type: Type of event
            message: Status message
            task_state: Current task state
            extra_payload: Additional payload data

        Returns:
            A2A-formatted event
        """
        payload = {"message": message, "stage": event_type}
        if extra_payload:
            payload.update(extra_payload)

        return {
            "jsonrpc": "2.0",
            "result": {
                "task": {"id": task_id, "state": task_state},
                "taskStatusUpdateEvent": {
                    "task": {
                        "id": task_id,
                        "state": task_state,
                        "messages": [
                            {
                                "role": "agent",
                                "parts": [{"type": "textPart", "text": message}],
                            }
                        ],
                    },
                    "final": False,
                },
                "metadata": {
                    "event_id": str(uuid.uuid4()),
                    "event_type": event_type,
                    "agent": "orchestrator",
                    "payload": payload,
                },
            },
        }

    def _create_error_event(
        self,
        task_id: str,
        message: str,
        stage: str,
    ) -> Dict[str, Any]:
        """Create an error event.

        Args:
            task_id: Task ID
            message: Error message
            stage: Stage where error occurred

        Returns:
            A2A-formatted error event
        """
        return {
            "jsonrpc": "2.0",
            "result": {
                "task": {"id": task_id, "state": "failed"},
                "taskStatusUpdateEvent": {
                    "task": {
                        "id": task_id,
                        "state": "failed",
                        "messages": [
                            {
                                "role": "agent",
                                "parts": [{"type": "textPart", "text": message}],
                            }
                        ],
                    },
                    "final": True,
                },
                "metadata": {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "error",
                    "agent": "orchestrator",
                    "payload": {"message": message, "stage": stage},
                },
            },
        }
