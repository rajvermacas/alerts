"""A2A AgentExecutor for the Wash Trade Alert Analyzer.

This module wraps the DeterministicWashTradeAgent as an A2A-compatible
executor, allowing it to be called via the A2A protocol.

Supports both synchronous execute() and async execute_stream() for SSE streaming.

Uses Proactive Information Flow architecture where data is injected via
AnalysisRequest rather than loaded from files.
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

from alerts.agents.wash_trade import DeterministicWashTradeAgent
from alerts.models.wash_trade import WashTradeDecision
from alerts.models.request import AnalysisRequest
from alerts.a2a.event_mapper import StreamEvent

logger = logging.getLogger(__name__)

# Prefix for Proactive Info Flow requests
PROACTIVE_INFO_FLOW_PREFIX = "PROACTIVE_INFO_FLOW_REQUEST:"


class WashTradeAgentExecutor(AgentExecutor):
    """A2A AgentExecutor that wraps the DeterministicWashTradeAgent.

    This executor receives wash trade alert analysis requests via A2A protocol
    and delegates to the deterministic agent for processing.

    Expects requests in Proactive Info Flow format:
    - Message starts with PROACTIVE_INFO_FLOW_REQUEST:
    - Followed by JSON AnalysisRequest payload
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
        self._agent: DeterministicWashTradeAgent | None = None
        logger.info("WashTradeAgentExecutor initialized")

    def _get_agent(self) -> DeterministicWashTradeAgent:
        """Get or create the deterministic agent.

        Returns:
            DeterministicWashTradeAgent instance
        """
        if self._agent is None:
            logger.info("Creating DeterministicWashTradeAgent instance")
            self._agent = DeterministicWashTradeAgent(
                llm=self.llm,
                data_dir=self.data_dir,
                output_dir=self.output_dir,
            )
        return self._agent

    def _is_proactive_info_flow_request(self, user_input: str) -> bool:
        """Check if the request is a Proactive Info Flow request.

        Args:
            user_input: Raw user input string

        Returns:
            True if this is a Proactive Info Flow request
        """
        return user_input.startswith(PROACTIVE_INFO_FLOW_PREFIX)

    def _parse_analysis_request(self, user_input: str) -> AnalysisRequest:
        """Parse AnalysisRequest from Proactive Info Flow message.

        Args:
            user_input: Message starting with PROACTIVE_INFO_FLOW_REQUEST:

        Returns:
            Parsed AnalysisRequest

        Raises:
            ValueError: If parsing fails
        """
        json_str = user_input[len(PROACTIVE_INFO_FLOW_PREFIX):]
        try:
            return AnalysisRequest.model_validate_json(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse AnalysisRequest: {e}") from e

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute the wash trade alert analysis.

        Args:
            context: Request context containing the message
            event_queue: Queue for sending events back to the client
        """
        logger.info("WashTradeAgentExecutor.execute called")

        # Validate request
        if self._validate_request(context):
            raise ServerError(error=InvalidParamsError())

        # Get user input
        user_input = context.get_user_input()
        logger.info(f"Received request: {user_input[:100]}...")

        # Create or get task
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            # Validate this is a Proactive Info Flow request
            if not self._is_proactive_info_flow_request(user_input):
                error_msg = (
                    "Invalid request format. Expected PROACTIVE_INFO_FLOW_REQUEST: prefix. "
                    "Legacy file-path mode is no longer supported."
                )
                logger.error(error_msg)
                await updater.update_status(
                    TaskState.input_required,
                    new_agent_text_message(error_msg, task.context_id, task.id),
                    final=True,
                )
                return

            decision = await self._execute_proactive_info_flow(
                user_input, updater, task
            )

            if decision is None:
                # Execution path that doesn't return a decision (e.g., input_required)
                return

            # Format result as text
            result = self._format_decision(decision)

            # Convert decision to dict for DataPart
            decision_dict = decision.model_dump(mode="json", exclude_none=True)

            # Add two artifacts: formatted text (for humans) and structured data (for machines)
            await updater.add_artifact(
                [Part(root=TextPart(text=result))],
                name="wash_trade_decision_text",
            )

            await updater.add_artifact(
                [Part(root=DataPart(data=decision_dict))],
                name="wash_trade_decision_json",
            )

            # Complete the task
            await updater.complete()
            logger.info(f"Wash trade analysis completed: {decision.determination}")

        except Exception as e:
            logger.error(f"Wash trade analysis failed: {e}", exc_info=True)
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

    async def _execute_proactive_info_flow(
        self,
        user_input: str,
        updater: TaskUpdater,
        task: Any,
    ) -> WashTradeDecision | None:
        """Execute analysis in Proactive Info Flow mode.

        Uses the deterministic agent with pre-aggregated data.

        Args:
            user_input: Raw input containing PROACTIVE_INFO_FLOW_REQUEST:...
            updater: Task updater for status updates
            task: Current task

        Returns:
            WashTradeDecision or None if error handled
        """
        logger.info("Executing in Proactive Info Flow mode")

        await updater.update_status(
            TaskState.working,
            new_agent_text_message(
                "Processing Proactive Info Flow request...",
                task.context_id,
                task.id,
            ),
        )

        # Parse the AnalysisRequest
        try:
            request = self._parse_analysis_request(user_input)
            logger.info(f"Parsed AnalysisRequest for agent_type: {request.agent_type}")
        except ValueError as e:
            logger.error(f"Failed to parse AnalysisRequest: {e}")
            await updater.update_status(
                TaskState.input_required,
                new_agent_text_message(
                    f"Invalid AnalysisRequest: {str(e)}",
                    task.context_id,
                    task.id,
                ),
                final=True,
            )
            return None

        # Validate agent type
        if request.agent_type != "wash_trade":
            error_msg = f"Invalid agent_type '{request.agent_type}' for WashTradeAgent"
            logger.error(error_msg)
            await updater.update_status(
                TaskState.input_required,
                new_agent_text_message(error_msg, task.context_id, task.id),
                final=True,
            )
            return None

        await updater.update_status(
            TaskState.working,
            new_agent_text_message(
                "Running deterministic analysis with pre-aggregated data...",
                task.context_id,
                task.id,
            ),
        )

        # Get deterministic agent and analyze
        agent = self._get_agent()
        decision = agent.analyze(request)

        return decision

    def _format_decision(self, decision: WashTradeDecision) -> str:
        """Format the wash trade decision as a readable string.

        Args:
            decision: WashTradeDecision to format

        Returns:
            Formatted string representation
        """
        lines = [
            "=" * 60,
            "WASH TRADE ALERT ANALYSIS RESULT",
            "=" * 60,
            f"",
            f"Alert ID: {decision.alert_id}",
            f"Alert Type: {decision.alert_type}",
            f"Determination: {decision.determination}",
            f"Genuine Confidence: {decision.genuine_alert_confidence}%",
            f"False Positive Confidence: {decision.false_positive_confidence}%",
            f"",
            "--- Pattern Analysis ---",
            f"Pattern Type: {decision.relationship_network.pattern_type}",
            f"Pattern Confidence: {decision.relationship_network.pattern_confidence}%",
            f"Pattern Description: {decision.relationship_network.pattern_description}",
            f"",
            f"Beneficial Ownership Match: {'Yes' if decision.beneficial_ownership_match else 'No'}",
            f"Economic Purpose Identified: {'Yes' if decision.economic_purpose_identified else 'No'}",
            f"Volume Impact: {decision.volume_impact_percentage:.1f}%",
            f"",
            "--- Timing Analysis ---",
            f"Time Delta: {decision.timing_patterns.time_delta_description}",
            f"Market Phase: {decision.timing_patterns.market_phase}",
            f"Pre-Arranged: {'Yes' if decision.timing_patterns.is_pre_arranged else 'No'} ({decision.timing_patterns.pre_arrangement_confidence}%)",
            f"",
            "--- Historical Patterns ---",
            f"Similar Patterns Found: {decision.historical_patterns.pattern_count}",
            f"Time Window: {decision.historical_patterns.time_window_days} days",
            f"Trend: {decision.historical_patterns.pattern_trend}",
            f"",
            f"Recommended Action: {decision.recommended_action}",
            f"Similar Precedent: {decision.similar_precedent}",
            f"",
            "--- Key Findings ---",
        ]

        for i, finding in enumerate(decision.key_findings, 1):
            lines.append(f"{i}. {finding}")

        lines.append("")
        lines.append("--- Favorable Indicators (suggesting genuine wash trade) ---")
        for indicator in decision.favorable_indicators:
            lines.append(f"  - {indicator}")

        lines.append("")
        lines.append("--- Risk Mitigating Factors (suggesting false positive) ---")
        for factor in decision.risk_mitigating_factors:
            lines.append(f"  - {factor}")

        if decision.regulatory_flags:
            lines.append("")
            lines.append("--- Regulatory Flags ---")
            for flag in decision.regulatory_flags:
                lines.append(f"  - {flag}")

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
        message: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute wash trade analysis with streaming events.

        This method streams progress events as the analysis progresses,
        yielding A2A-formatted events that can be sent via SSE.

        Expects Proactive Info Flow mode (AnalysisRequest JSON prefixed
        with PROACTIVE_INFO_FLOW_REQUEST:).

        Args:
            task_id: Task ID for event correlation
            message: Message containing PROACTIVE_INFO_FLOW_REQUEST:...

        Yields:
            Dict containing A2A-formatted streaming events

        Raises:
            ValueError: If AnalysisRequest is invalid
            Exception: If analysis fails
        """
        logger.info(f"Starting streaming wash trade analysis for task {task_id}")

        # Validate this is a Proactive Info Flow request
        if not self._is_proactive_info_flow_request(message):
            error_msg = (
                "Invalid request format. Expected PROACTIVE_INFO_FLOW_REQUEST: prefix. "
                "Legacy file-path mode is no longer supported."
            )
            logger.error(error_msg)
            error_event = {
                "event_type": "error",
                "task_id": task_id,
                "agent": "wash_trade",
                "payload": {
                    "message": error_msg,
                    "stage": "initialization",
                },
                "final": True,
            }
            yield self._wrap_event_for_a2a(error_event, task_id, "failed")
            return

        # Parse the AnalysisRequest
        try:
            request = self._parse_analysis_request(message)
            logger.info(f"Parsed AnalysisRequest for agent_type: {request.agent_type}")
        except ValueError as e:
            logger.error(f"Failed to parse AnalysisRequest: {e}")
            error_event = {
                "event_type": "error",
                "task_id": task_id,
                "agent": "wash_trade",
                "payload": {
                    "message": f"Invalid AnalysisRequest: {str(e)}",
                    "stage": "initialization",
                },
                "final": True,
            }
            yield self._wrap_event_for_a2a(error_event, task_id, "failed")
            return

        # Validate agent type
        if request.agent_type != "wash_trade":
            error_msg = f"Invalid agent_type '{request.agent_type}' for WashTradeAgent"
            logger.error(error_msg)
            error_event = {
                "event_type": "error",
                "task_id": task_id,
                "agent": "wash_trade",
                "payload": {
                    "message": error_msg,
                    "stage": "initialization",
                },
                "final": True,
            }
            yield self._wrap_event_for_a2a(error_event, task_id, "failed")
            return

        # Get deterministic agent
        agent = self._get_agent()

        # Stream events from deterministic agent
        try:
            async for event in agent.astream_analyze(request, task_id):
                # Convert StreamEvent to A2A format
                a2a_event = event.to_a2a_format(
                    task_state="completed" if event.final else "working"
                )
                yield a2a_event

        except Exception as e:
            logger.error(f"Proactive Info Flow streaming failed: {e}", exc_info=True)
            error_event = {
                "event_type": "error",
                "task_id": task_id,
                "agent": "wash_trade",
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
