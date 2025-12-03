"""A2A AgentExecutor for the Orchestrator Agent.

This module wraps the OrchestratorAgent as an A2A-compatible executor,
allowing it to receive alert analysis requests via the A2A protocol.
"""

import json
import logging
from pathlib import Path

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
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

            # Add artifact with the result
            await updater.add_artifact(
                [Part(root=TextPart(text=response_text))],
                name="orchestrator_result",
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
