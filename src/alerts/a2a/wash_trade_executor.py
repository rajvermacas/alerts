"""A2A AgentExecutor for the Wash Trade Alert Analyzer.

This module wraps the WashTradeAnalyzerAgent as an A2A-compatible
executor, allowing it to be called via the A2A protocol.
"""

import logging
from pathlib import Path
from typing import Any

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

from alerts.agents.wash_trade import WashTradeAnalyzerAgent
from alerts.models.wash_trade import WashTradeDecision

logger = logging.getLogger(__name__)


class WashTradeAgentExecutor(AgentExecutor):
    """A2A AgentExecutor that wraps the WashTradeAnalyzerAgent.

    This executor receives wash trade alert analysis requests via A2A protocol
    and delegates to the WashTradeAnalyzerAgent for processing.
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
        self._agent: WashTradeAnalyzerAgent | None = None
        logger.info("WashTradeAgentExecutor initialized")

    def _get_agent(self) -> WashTradeAnalyzerAgent:
        """Get or create the WashTradeAnalyzerAgent instance.

        Returns:
            WashTradeAnalyzerAgent instance
        """
        if self._agent is None:
            logger.info("Creating WashTradeAnalyzerAgent instance")
            self._agent = WashTradeAnalyzerAgent(
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
        """Execute the wash trade alert analysis.

        Args:
            context: Request context containing the message
            event_queue: Queue for sending events back to the client
        """
        logger.info("WashTradeAgentExecutor.execute called")

        # Validate request
        if self._validate_request(context):
            raise ServerError(error=InvalidParamsError())

        # Get user input (alert file path)
        user_input = context.get_user_input()
        logger.info(f"Received request to analyze wash trade alert: {user_input}")

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
                    "Starting wash trade alert analysis...",
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
                        "Please provide the path to the wash trade alert XML file to analyze.",
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
                    # Try in wash_trade subdirectory
                    alert_file = self.data_dir / "alerts" / "wash_trade" / Path(alert_path).name
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
                    f"Analyzing wash trade alert file: {alert_file}",
                    task.context_id,
                    task.id,
                ),
            )

            # Get agent and analyze
            agent = self._get_agent()
            decision: WashTradeDecision = agent.analyze(alert_file)

            # Format result as text
            result = self._format_decision(decision)

            # Convert decision to JSON
            decision_json = decision.model_dump_json(indent=2, exclude_none=True)

            # Add two artifacts: formatted text and JSON
            await updater.add_artifact(
                [Part(root=TextPart(text=result))],
                name="wash_trade_decision_text",
            )

            await updater.add_artifact(
                [Part(root=TextPart(text=decision_json))],
                name="wash_trade_decision_json",
            )

            # Complete the task
            await updater.complete()
            logger.info(f"Wash trade analysis completed: {decision.determination}")

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
