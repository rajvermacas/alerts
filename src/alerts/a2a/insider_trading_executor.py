"""A2A AgentExecutor for the Insider Trading Alert Analyzer.

This module wraps the existing AlertAnalyzerAgent as an A2A-compatible
executor, allowing it to be called via the A2A protocol.

Supports both synchronous execute() and async execute_stream() for SSE streaming.
"""

import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict

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

from alerts.agent import AlertAnalyzerAgent
from alerts.models import AlertDecision
from alerts.a2a.event_mapper import StreamEvent

logger = logging.getLogger(__name__)


class InsiderTradingAgentExecutor(AgentExecutor):
    """A2A AgentExecutor that wraps the AlertAnalyzerAgent.

    This executor receives alert analysis requests via A2A protocol
    and delegates to the existing AlertAnalyzerAgent for processing.
    """

    def __init__(self, llm: Any, data_dir: Path, output_dir: Path) -> None:
        """Initialize the executor with required dependencies.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory containing test data
            output_dir: Path for output reports
        """
        self.llm = llm
        self.data_dir = data_dir
        self.output_dir = output_dir
        self._agent: AlertAnalyzerAgent | None = None
        logger.info("InsiderTradingAgentExecutor initialized")

    def _get_agent(self) -> AlertAnalyzerAgent:
        """Get or create the AlertAnalyzerAgent instance.

        Returns:
            AlertAnalyzerAgent instance
        """
        if self._agent is None:
            logger.info("Creating AlertAnalyzerAgent instance")
            self._agent = AlertAnalyzerAgent(
                llm=self.llm,
                data_dir=self.data_dir,
                output_dir=self.output_dir,
            )
        return self._agent

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute the insider trading alert analysis.

        Args:
            context: Request context containing the message
            event_queue: Queue for sending events back to the client
        """
        logger.info("InsiderTradingAgentExecutor.execute called")

        # Validate request
        if self._validate_request(context):
            raise ServerError(error=InvalidParamsError())

        # Get user input (alert file path)
        user_input = context.get_user_input()
        logger.info(f"Received request to analyze: {user_input}")

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
                    "Starting insider trading alert analysis...",
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
                alert_file = self.data_dir / alert_path
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

            # Update status - analyzing
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    f"Analyzing alert file: {alert_file}",
                    task.context_id,
                    task.id,
                ),
            )

            # Get agent and analyze
            agent = self._get_agent()
            decision: AlertDecision = agent.analyze(alert_file)

            # Format result as text
            result = self._format_decision(decision)

            # Convert decision to dict for DataPart
            decision_dict = decision.model_dump(mode="json", exclude_none=True)

            # Add two artifacts: formatted text (for humans) and structured data (for machines)
            await updater.add_artifact(
                [Part(root=TextPart(text=result))],
                name="alert_decision_text",
            )

            await updater.add_artifact(
                [Part(root=DataPart(data=decision_dict))],
                name="alert_decision_json",
            )

            # Complete the task
            await updater.complete()
            logger.info(f"Analysis completed: {decision.determination}")

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
            logger.error(f"Analysis failed: {e}", exc_info=True)
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
            # Extract path containing .xml
            words = user_input.split()
            for word in words:
                if ".xml" in word.lower():
                    # Clean up the path
                    path = word.strip("'\"")
                    return path

        # If the entire input looks like a path
        if "/" in user_input or user_input.endswith(".xml"):
            return user_input.strip()

        # Check if it's just asking to analyze with a specific alert
        for keyword in ["analyze", "check", "review"]:
            if keyword in input_lower:
                # Look for path after the keyword
                parts = user_input.split(keyword)
                if len(parts) > 1:
                    remaining = parts[1].strip()
                    if remaining:
                        return remaining.split()[0].strip("'\"")

        return user_input.strip() if user_input.strip() else None

    def _format_decision(self, decision: AlertDecision) -> str:
        """Format the decision as a readable string.

        Args:
            decision: AlertDecision to format

        Returns:
            Formatted string representation
        """
        lines = [
            "=" * 60,
            "INSIDER TRADING ALERT ANALYSIS RESULT",
            "=" * 60,
            f"",
            f"Alert ID: {decision.alert_id}",
            f"Determination: {decision.determination}",
            f"Genuine Confidence: {decision.genuine_alert_confidence}%",
            f"False Positive Confidence: {decision.false_positive_confidence}%",
            f"",
            f"Recommended Action: {decision.recommended_action}",
            f"Similar Precedent: {decision.similar_precedent}",
            f"",
            "--- Key Findings ---",
        ]

        for i, finding in enumerate(decision.key_findings, 1):
            lines.append(f"{i}. {finding}")

        lines.append("")
        lines.append("--- Favorable Indicators (suggesting genuine) ---")
        for indicator in decision.favorable_indicators:
            lines.append(f"  - {indicator}")

        lines.append("")
        lines.append("--- Risk Mitigating Factors (suggesting false positive) ---")
        for factor in decision.risk_mitigating_factors:
            lines.append(f"  - {factor}")

        lines.append("")
        lines.append("--- Reasoning ---")
        lines.append(decision.reasoning_narrative)

        if decision.data_gaps:
            lines.append("")
            lines.append("--- Data Gaps ---")
            for gap in decision.data_gaps:
                lines.append(f"  - {gap}")

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
        """Execute analysis with streaming events.

        This method streams progress events as the analysis progresses,
        yielding A2A-formatted events that can be sent via SSE.

        Args:
            task_id: Task ID for event correlation
            alert_path: Path to the alert XML file

        Yields:
            Dict containing A2A-formatted streaming events

        Raises:
            FileNotFoundError: If alert file doesn't exist
            Exception: If analysis fails
        """
        logger.info(f"Starting streaming analysis for task {task_id}: {alert_path}")

        # Resolve alert file path
        alert_file = Path(alert_path)
        if not alert_file.exists():
            alert_file = self.data_dir / alert_path
            if not alert_file.exists():
                error_event = {
                    "event_type": "error",
                    "task_id": task_id,
                    "agent": "insider_trading",
                    "payload": {
                        "message": f"Alert file not found: {alert_path}",
                        "stage": "initialization",
                    },
                    "final": True,
                }
                yield self._wrap_event_for_a2a(error_event, task_id, "failed")
                return

        # Get or create agent
        agent = self._get_agent()

        # Stream events from agent
        try:
            async for event in agent.astream_analyze(alert_file, task_id):
                # Convert StreamEvent to A2A format
                a2a_event = event.to_a2a_format(
                    task_state="completed" if event.final else "working"
                )
                yield a2a_event

        except FileNotFoundError as e:
            logger.error(f"File not found during streaming: {e}")
            error_event = {
                "event_type": "error",
                "task_id": task_id,
                "agent": "insider_trading",
                "payload": {
                    "message": str(e),
                    "stage": "analysis",
                },
                "final": True,
            }
            yield self._wrap_event_for_a2a(error_event, task_id, "failed")

        except Exception as e:
            logger.error(f"Streaming analysis failed: {e}", exc_info=True)
            error_event = {
                "event_type": "error",
                "task_id": task_id,
                "agent": "insider_trading",
                "payload": {
                    "message": f"Analysis failed: {str(e)}",
                    "stage": "analysis",
                },
                "final": True,
            }
            yield self._wrap_event_for_a2a(error_event, task_id, "failed")

    def _wrap_event_for_a2a(
        self,
        event: Dict[str, Any],
        task_id: str,
        task_state: str,
    ) -> Dict[str, Any]:
        """Wrap a raw event dict in A2A format.

        Args:
            event: Raw event dictionary
            task_id: Task ID
            task_state: Current task state

        Returns:
            A2A-formatted event
        """
        return {
            "jsonrpc": "2.0",
            "result": {
                "task": {
                    "id": task_id,
                    "state": task_state,
                },
                "taskStatusUpdateEvent": {
                    "task": {
                        "id": task_id,
                        "state": task_state,
                        "messages": [
                            {
                                "role": "agent",
                                "parts": [
                                    {
                                        "type": "textPart",
                                        "text": event.get("payload", {}).get("message", "Processing..."),
                                    }
                                ],
                            }
                        ],
                    },
                    "final": event.get("final", False),
                },
                "metadata": event,
            },
        }
