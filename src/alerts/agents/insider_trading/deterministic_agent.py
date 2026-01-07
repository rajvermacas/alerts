"""Deterministic Insider Trading Agent for Proactive Info Flow.

This module implements a deterministic agent that:
1. Receives pre-aggregated data via AnalysisRequest
2. Executes tools in a fixed order (no LLM-based routing)
3. Uses LLM only for tool-level interpretation and final synthesis

This replaces the LangGraph-based agent with a simple Python loop.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from alerts.a2a.event_mapper import EventMapper, StreamEvent
from alerts.models.insider_trading import InsiderTradingDecision
from alerts.models.request import (
    AnalysisRequest,
    MissingToolDataError,
    INSIDER_TRADING_REQUIRED_TOOLS,
)
from alerts.reports.html_generator import HTMLReportGenerator
from alerts.agents.insider_trading.prompts.system_prompt import (
    get_final_decision_prompt,
    get_system_prompt,
    load_few_shot_examples,
)
from alerts.tools.common import (
    AlertReaderTool,
    TraderProfileTool,
    MarketDataTool,
)
from alerts.agents.insider_trading.tools import (
    TraderHistoryTool,
    MarketNewsTool,
)

logger = logging.getLogger(__name__)


# Fixed tool execution order for Insider Trading analysis
# This is the canonical definition - no LLM routing involved
TOOL_ORDER: Tuple[str, ...] = (
    "alert_reader",
    "market_news",
    "market_data",
    "trader_profile",
    "trader_history",
)


class DeterministicInsiderTradingAgent:
    """Deterministic agent for Insider Trading alert analysis.

    This agent executes tools in a fixed order and uses LLM only for:
    1. Tool-level data interpretation (inside each tool)
    2. Final synthesis to produce InsiderTradingDecision

    Key differences from LangGraph-based agent:
    - No LLM-based tool selection (TOOL_ORDER is hardcoded)
    - Data is injected via AnalysisRequest, not loaded by tools
    - Simple Python loop instead of graph execution
    - More predictable and reproducible behavior

    Attributes:
        llm: LangChain LLM instance for synthesis
        output_dir: Path to output directory for reports
        few_shot_examples: List of few-shot examples for LLM prompts
        tool_instances: Dict mapping tool names to tool instances
    """

    def __init__(
        self,
        llm: Any,
        data_dir: Path,
        output_dir: Path,
    ) -> None:
        """Initialize the deterministic agent.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory (for few-shot examples)
            output_dir: Path for output reports
        """
        self.llm = llm
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.logger = logger

        self.logger.info("=" * 60)
        self.logger.info("Initializing DeterministicInsiderTradingAgent")
        self.logger.info("=" * 60)
        self.logger.info(f"Data directory: {data_dir}")
        self.logger.info(f"Output directory: {output_dir}")
        self.logger.info(f"Tool execution order: {TOOL_ORDER}")

        # Validate tool order matches required tools
        if set(TOOL_ORDER) != INSIDER_TRADING_REQUIRED_TOOLS:
            missing = INSIDER_TRADING_REQUIRED_TOOLS - set(TOOL_ORDER)
            extra = set(TOOL_ORDER) - INSIDER_TRADING_REQUIRED_TOOLS
            raise ValueError(
                f"TOOL_ORDER mismatch with required tools. "
                f"Missing: {missing}, Extra: {extra}"
            )

        # Load few-shot examples
        examples_path = data_dir / "few_shot_examples.json"
        self.few_shot_examples = load_few_shot_examples(examples_path)
        if not self.few_shot_examples:
            raise FileNotFoundError(f"Few-shot examples not found: {examples_path}")
        self.logger.info(f"Loaded {len(self.few_shot_examples)} few-shot examples")

        # Initialize tool instances (keyed by name for easy lookup)
        self.tool_instances = self._create_tool_instances()
        self.logger.info(f"Created {len(self.tool_instances)} tool instances")

        self.logger.info("DeterministicInsiderTradingAgent initialized successfully")

    def _create_tool_instances(self) -> Dict[str, Any]:
        """Create tool instances keyed by name.

        Returns:
            Dict mapping tool names to tool instances
        """
        tools = {
            "alert_reader": AlertReaderTool(self.llm),
            "trader_profile": TraderProfileTool(self.llm),
            "market_data": MarketDataTool(self.llm),
            "trader_history": TraderHistoryTool(self.llm),
            "market_news": MarketNewsTool(self.llm),
        }

        # Validate all required tools are present
        for tool_name in TOOL_ORDER:
            if tool_name not in tools:
                raise ValueError(f"Missing tool implementation: {tool_name}")

        return tools

    def analyze(self, request: AnalysisRequest) -> InsiderTradingDecision:
        """Analyze an alert and produce a determination.

        This is the main entry point for synchronous analysis.
        Executes tools in fixed order and synthesizes final decision.

        Args:
            request: AnalysisRequest with pre-aggregated tool data

        Returns:
            InsiderTradingDecision with determination and reasoning

        Raises:
            MissingToolDataError: If required tool data is missing
            ValueError: If analysis fails
        """
        start_time = datetime.now(timezone.utc)

        self.logger.info("=" * 60)
        self.logger.info("Starting deterministic insider trading analysis")
        self.logger.info(f"Agent type: {request.agent_type}")
        self.logger.info(f"Tools to execute: {TOOL_ORDER}")
        self.logger.info("=" * 60)

        # Validate request is for insider trading
        if request.agent_type != "insider_trading":
            raise ValueError(
                f"Invalid agent_type for InsiderTradingAgent: {request.agent_type}"
            )

        # Execute tools in fixed order and collect insights
        insights: Dict[str, str] = {}

        for tool_name in TOOL_ORDER:
            self.logger.info(f"[{tool_name}] Starting tool execution")

            # Get tool data from request (validated to exist by Pydantic)
            tool_input = request.get_tool_data(tool_name)
            self.logger.debug(
                f"[{tool_name}] Data format: {tool_input.format}, "
                f"length: {len(tool_input.data)}"
            )

            # Get tool instance
            tool = self.tool_instances[tool_name]

            # Execute tool with injected data
            try:
                insight = tool.execute(
                    data=tool_input.data,
                    data_format=tool_input.format,
                )
                insights[tool_name] = insight
                self.logger.info(
                    f"[{tool_name}] Completed - insight length: {len(insight)}"
                )

            except Exception as e:
                self.logger.error(f"[{tool_name}] Failed: {e}", exc_info=True)
                # Fail-fast: re-raise the exception
                raise

        # Synthesize final decision
        self.logger.info("All tools completed. Starting final synthesis.")
        decision = self._synthesize_decision(insights)

        # Calculate processing time
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        self.logger.info(f"Analysis completed in {elapsed:.2f}s")
        self.logger.info(
            f"Decision: {decision.determination} "
            f"(genuine: {decision.genuine_alert_confidence}%, "
            f"false_positive: {decision.false_positive_confidence}%)"
        )

        # Write outputs
        self._write_decision(decision)
        self._write_html_report_from_xml(decision, request.alert_xml)
        self._write_audit_log(decision, elapsed)

        return decision

    async def astream_analyze(
        self,
        request: AnalysisRequest,
        task_id: str,
    ) -> AsyncIterator[StreamEvent]:
        """Analyze an alert with streaming events.

        This async generator yields StreamEvent objects as the analysis
        progresses, enabling real-time progress updates to clients.

        Args:
            request: AnalysisRequest with pre-aggregated tool data
            task_id: Task ID for event correlation

        Yields:
            StreamEvent objects for each progress update

        Raises:
            MissingToolDataError: If required tool data is missing
            ValueError: If analysis fails
        """
        start_time = datetime.now(timezone.utc)
        event_mapper = EventMapper(task_id=task_id, agent_name="insider_trading")

        self.logger.info("=" * 60)
        self.logger.info("Starting streaming deterministic analysis")
        self.logger.info(f"Task ID: {task_id}")
        self.logger.info(f"Agent type: {request.agent_type}")
        self.logger.info("=" * 60)

        # Validate request is for insider trading
        if request.agent_type != "insider_trading":
            error_msg = f"Invalid agent_type: {request.agent_type}"
            yield event_mapper.create_error_event(
                error_msg, stage="validation", fatal=True
            )
            raise ValueError(error_msg)

        # Emit analysis started event
        yield event_mapper.create_analysis_started_event(
            f"insider_trading_analysis:{task_id}"
        )

        # Execute tools in fixed order and collect insights
        insights: Dict[str, str] = {}

        for tool_name in TOOL_ORDER:
            self.logger.info(f"[{tool_name}] Starting tool execution")

            # Emit tool started event
            yield event_mapper.create_tool_started_event(tool_name)

            # Get tool data from request
            try:
                tool_input = request.get_tool_data(tool_name)
            except MissingToolDataError as e:
                yield event_mapper.create_error_event(
                    str(e), stage=f"tool:{tool_name}", fatal=True
                )
                raise

            # Get tool instance
            tool = self.tool_instances[tool_name]

            # Execute tool with injected data
            try:
                insight = tool.execute(
                    data=tool_input.data,
                    data_format=tool_input.format,
                )
                insights[tool_name] = insight

                # Emit tool completed event
                yield event_mapper.create_tool_completed_event(
                    tool_name=tool_name,
                    result_preview=insight[:200] + "..." if len(insight) > 200 else insight,
                )
                self.logger.info(f"[{tool_name}] Completed")

            except Exception as e:
                self.logger.error(f"[{tool_name}] Failed: {e}", exc_info=True)
                yield event_mapper.create_error_event(
                    str(e), stage=f"tool:{tool_name}", fatal=True
                )
                raise

        # Emit evaluation started event
        yield event_mapper.create_evaluation_started_event()

        # Synthesize final decision
        self.logger.info("Starting final synthesis")
        try:
            decision = self._synthesize_decision(insights)
        except Exception as e:
            self.logger.error(f"Synthesis failed: {e}", exc_info=True)
            yield event_mapper.create_error_event(
                str(e), stage="synthesis", fatal=True
            )
            raise

        # Calculate processing time
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Write outputs
        self._write_decision(decision)
        self._write_html_report_from_xml(decision, request.alert_xml)
        self._write_audit_log(decision, elapsed)

        # Emit completion event
        decision_dict = decision.model_dump(mode="json", exclude_none=True)
        yield event_mapper.create_analysis_complete_event(
            determination=decision.determination,
            confidence=decision.genuine_alert_confidence,
            summary=decision.key_findings[0] if decision.key_findings else "Analysis complete",
            decision=decision_dict,
        )

        self.logger.info(
            f"Streaming analysis completed in {elapsed:.2f}s: "
            f"{decision.determination}"
        )

    def _synthesize_decision(
        self,
        insights: Dict[str, str],
    ) -> InsiderTradingDecision:
        """Synthesize final decision from tool insights.

        This is the only agentic reasoning step - all tool insights
        are combined with the system prompt and few-shot examples
        to produce the final structured decision.

        Args:
            insights: Dict mapping tool names to their insights

        Returns:
            InsiderTradingDecision with determination and reasoning

        Raises:
            ValueError: If LLM fails to produce valid decision
        """
        self.logger.info("Building synthesis prompt with all insights")

        # Build system prompt with few-shot examples
        system_prompt = get_system_prompt(self.few_shot_examples)

        # Format insights for inclusion in prompt
        insights_text = self._format_insights_for_prompt(insights)

        # Build the synthesis message
        synthesis_message = f"""Based on the following tool outputs, provide your final determination for this insider trading alert.

## Tool Analysis Results

{insights_text}

## Instructions

{get_final_decision_prompt()}

Provide your complete analysis and determination."""

        # Create messages for LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=synthesis_message),
        ]

        self.logger.debug(f"Synthesis prompt length: {len(synthesis_message)}")

        # Invoke LLM with structured output
        llm_structured = self.llm.with_structured_output(InsiderTradingDecision)
        decision = llm_structured.invoke(messages)

        if decision is None:
            self._log_failed_synthesis(insights, messages)
            raise ValueError(
                "LLM returned None for structured decision. "
                "Check resources/debug/ for details."
            )

        return decision

    def _format_insights_for_prompt(self, insights: Dict[str, str]) -> str:
        """Format tool insights for inclusion in synthesis prompt.

        Args:
            insights: Dict mapping tool names to their insights

        Returns:
            Formatted string with all insights
        """
        formatted_parts = []

        for tool_name in TOOL_ORDER:
            if tool_name in insights:
                insight = insights[tool_name]
                formatted_parts.append(f"### {tool_name.replace('_', ' ').title()}\n\n{insight}")

        return "\n\n---\n\n".join(formatted_parts)

    def _log_failed_synthesis(
        self,
        insights: Dict[str, str],
        messages: List[Any],
    ) -> None:
        """Log failed synthesis attempt to debug file.

        Args:
            insights: Tool insights that were used
            messages: Messages sent to LLM
        """
        debug_dir = Path("resources/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        debug_file = debug_dir / f"deterministic_it_failed_{timestamp}.json"

        debug_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "LLM returned None for structured decision",
            "insights_count": len(insights),
            "insights_lengths": {k: len(v) for k, v in insights.items()},
            "messages_count": len(messages),
        }

        debug_file.write_text(json.dumps(debug_data, indent=2, default=str))
        self.logger.error(f"Failed synthesis logged to {debug_file.absolute()}")

    def _write_decision(self, decision: InsiderTradingDecision) -> Path:
        """Write decision to JSON file.

        Args:
            decision: InsiderTradingDecision to write

        Returns:
            Path to written file
        """
        output_file = self.output_dir / f"decision_{decision.alert_id}.json"

        self.logger.info(f"Writing decision to {output_file}")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(decision.model_dump_json(indent=2))

        return output_file

    def _write_html_report_from_xml(
        self,
        decision: InsiderTradingDecision,
        alert_xml: str,
    ) -> Path:
        """Write HTML report from XML content.

        Args:
            decision: InsiderTradingDecision to include in report
            alert_xml: Raw XML content of the alert

        Returns:
            Path to written HTML file
        """
        output_file = self.output_dir / f"decision_{decision.alert_id}.html"

        self.logger.info(f"Writing HTML report to {output_file}")

        try:
            generator = HTMLReportGenerator.from_xml_string(alert_xml, decision)
            html_content = generator.generate()

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html_content)

            self.logger.info(f"HTML report written successfully: {output_file}")
            return output_file

        except Exception as e:
            self.logger.error(f"Failed to write HTML report: {e}", exc_info=True)
            raise

    def _write_audit_log(
        self,
        decision: InsiderTradingDecision,
        processing_time: float,
    ) -> None:
        """Append to audit log.

        Args:
            decision: InsiderTradingDecision to log
            processing_time: Processing time in seconds
        """
        audit_file = self.output_dir / "audit_log.jsonl"

        self.logger.info(f"Appending to audit log: {audit_file}")

        audit_entry = decision.to_audit_entry()
        audit_entry["processing_time_seconds"] = round(processing_time, 2)
        audit_entry["agent_type"] = "deterministic_insider_trading"

        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")

    def get_tool_stats(self) -> Dict[str, Any]:
        """Get statistics about tool usage.

        Returns:
            Dictionary with tool statistics
        """
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_type": "deterministic_insider_trading",
            "tool_order": TOOL_ORDER,
            "tools": [
                self.tool_instances[name].get_stats()
                for name in TOOL_ORDER
            ],
        }
