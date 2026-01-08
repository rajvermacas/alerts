"""Deterministic agent for Wash Trade Alert Analysis.

This module implements the wash trade analyzer agent that orchestrates
tool calls in a fixed order and produces the final determination for
wash trade alerts.

Supports both synchronous analyze() and async astream_analyze() for real-time streaming.

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                    AnalysisRequest                       │
    │  (alert_xml, agent_type, tool_data: Dict[str, ToolInput])│
    └─────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────┐
    │                 WashTradeAnalyzerAgent                   │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │  TOOL_ORDER = [                                     │ │
    │  │    "alert_reader",                                  │ │
    │  │    "market_data",                                   │ │
    │  │    "account_relationships",                         │ │
    │  │    "related_accounts_history",                      │ │
    │  │    "trade_timing",                                  │ │
    │  │    "counterparty_analysis",                         │ │
    │  │  ]                                                  │ │
    │  └────────────────────────────────────────────────────┘ │
    │                         │                                │
    │       for tool_name in TOOL_ORDER:                       │
    │           emit("tool_started", tool_name)                │
    │           insight = tool.execute(data, format)           │
    │           insights[tool_name] = insight                  │
    │           emit("tool_completed", tool_name)              │
    │                         │                                │
    │                         ▼                                │
    │              _synthesize(insights)                       │
    │                  (LLM call)                              │
    └─────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       WashTradeDecision
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from alerts.a2a.event_mapper import EventMapper, StreamEvent
from alerts.exceptions import MissingToolDataError
from alerts.models.wash_trade import WashTradeDecision
from alerts.models.request import AnalysisRequest, ToolInput
from alerts.reports.wash_trade_report import WashTradeHTMLReportGenerator
from alerts.agents.wash_trade.prompts.system_prompt import (
    get_wash_trade_system_prompt,
    get_wash_trade_final_decision_prompt,
    load_wash_trade_few_shot_examples,
)
from alerts.tools.common import (
    AlertReaderTool,
    MarketDataTool,
)
from alerts.agents.wash_trade.tools import (
    AccountRelationshipsTool,
    RelatedAccountsHistoryTool,
    TradeTimingTool,
    CounterpartyAnalysisTool,
)

logger = logging.getLogger(__name__)


class WashTradeAnalyzerAgent:
    """Deterministic agent for analyzing SMARTS wash trade alerts.

    This agent uses a fixed tool order approach to gather evidence and
    produce a structured determination for wash trade alerts.
    No LLM routing is used - tools are executed in a predetermined order.

    The agent focuses on:
    - Beneficial ownership analysis
    - Trade timing patterns
    - Counterparty flow detection
    - Historical pattern analysis
    - APAC regulatory framework application

    Attributes:
        llm: LangChain LLM instance
        data_dir: Path to data directory
        output_dir: Path to output directory
        tool_instances: Dict mapping tool names to instances
    """

    # Fixed order of tool execution - no LLM routing needed
    # Note: trader_profile is NOT included for wash trade (per user decision)
    TOOL_ORDER: List[str] = [
        "read_alert",
        "query_market_data",
        "account_relationships",
        "related_accounts_history",
        "trade_timing",
        "counterparty_analysis",
    ]

    def __init__(
        self,
        llm: Any,
        data_dir: Path,
        output_dir: Path,
    ) -> None:
        """Initialize the agent.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory containing test data
            output_dir: Path for output reports
        """
        self.llm = llm
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.logger = logger

        self.logger.info("Initializing WashTradeAnalyzerAgent (Deterministic)")
        self.logger.info(f"Data directory: {data_dir}")
        self.logger.info(f"Output directory: {output_dir}")

        # Load few-shot examples (optional - may not exist yet)
        self.few_shot_examples = load_wash_trade_few_shot_examples(str(data_dir))
        if self.few_shot_examples:
            self.logger.info(f"Loaded {len(self.few_shot_examples.examples)} few-shot examples")
        else:
            self.logger.warning("No wash trade few-shot examples loaded - using base prompts")

        # Initialize tool instances as a dict for name-based lookup
        self.tool_instances = self._create_tool_instances()
        self.logger.info(f"Created {len(self.tool_instances)} tool instances")
        self.logger.info(f"Tool execution order: {self.TOOL_ORDER}")

    def _create_tool_instances(self) -> Dict[str, Any]:
        """Create instances of all analysis tools.

        Returns:
            Dict mapping tool names to tool instances
        """
        data_dir_str = str(self.data_dir)

        tools = [
            # Common tools
            AlertReaderTool(self.llm, self.data_dir),
            MarketDataTool(self.llm, self.data_dir),
            # Wash trade specific tools
            AccountRelationshipsTool(self.llm, data_dir_str),
            RelatedAccountsHistoryTool(self.llm, data_dir_str),
            TradeTimingTool(self.llm, data_dir_str),
            CounterpartyAnalysisTool(self.llm, data_dir_str),
        ]
        return {tool.name: tool for tool in tools}

    def _get_tool_data_key(self, tool_name: str) -> str:
        """Map internal tool names to AnalysisRequest tool_data keys.

        Args:
            tool_name: Internal tool name (e.g., "read_alert")

        Returns:
            Key to use in AnalysisRequest.tool_data (e.g., "alert_reader")
        """
        # Map from internal tool names to request.tool_data keys
        tool_key_map = {
            "read_alert": "alert_reader",
            "query_market_data": "market_data",
            "account_relationships": "account_relationships",
            "related_accounts_history": "related_accounts_history",
            "trade_timing": "trade_timing",
            "counterparty_analysis": "counterparty_analysis",
        }
        return tool_key_map.get(tool_name, tool_name)

    def analyze_request(
        self,
        request: AnalysisRequest,
        event_callback: Optional[Callable[[str, str, Optional[Dict]], None]] = None,
    ) -> WashTradeDecision:
        """Analyze an alert using the proactive info flow pattern.

        This method uses data injected via AnalysisRequest instead of
        loading data from files.

        Args:
            request: AnalysisRequest with alert_xml, agent_type, and tool_data
            event_callback: Optional callback for emitting events
                           Signature: (event_type, tool_name, data) -> None

        Returns:
            WashTradeDecision with the determination and reasoning

        Raises:
            MissingToolDataError: If required tool data is not provided
            Exception: If analysis fails
        """
        start_time = datetime.now(timezone.utc)

        self.logger.info("=" * 60)
        self.logger.info("Starting deterministic wash trade analysis")
        self.logger.info(f"Agent type: {request.agent_type}")
        self.logger.info(f"Tool data keys: {list(request.tool_data.keys())}")
        self.logger.info("=" * 60)

        insights: Dict[str, str] = {}

        # Execute tools in fixed order
        for tool_name in self.TOOL_ORDER:
            tool_data_key = self._get_tool_data_key(tool_name)

            self.logger.info(f"Executing tool: {tool_name} (data key: {tool_data_key})")

            # Get tool data from request
            tool_input = request.tool_data.get(tool_data_key)
            if tool_input is None:
                raise MissingToolDataError(tool_data_key)

            # Emit tool started event
            if event_callback:
                event_callback("tool_started", tool_name, None)

            # Get tool instance and execute with injected data
            tool = self.tool_instances.get(tool_name)
            if tool is None:
                raise ValueError(f"Unknown tool: {tool_name}")

            try:
                insight = tool.execute(
                    data=tool_input.data,
                    format=tool_input.format,
                )
                insights[tool_name] = insight
                self.logger.info(f"Tool {tool_name} completed successfully")

                # Emit tool completed event
                if event_callback:
                    event_callback("tool_completed", tool_name, {"insight_length": len(insight)})

            except Exception as e:
                self.logger.error(f"Tool {tool_name} failed: {e}")
                if event_callback:
                    event_callback("tool_error", tool_name, {"error": str(e)})
                raise

        # Emit evaluation started event
        if event_callback:
            event_callback("evaluation_started", "synthesis", None)

        # Synthesize final decision using LLM
        decision = self._synthesize(insights)

        # Calculate processing time
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        self.logger.info(f"Wash trade analysis completed in {elapsed:.2f}s")

        # Write outputs
        self._write_decision(decision)
        self._write_audit_log(decision, elapsed)

        # Emit completion event
        if event_callback:
            event_callback("analysis_complete", "synthesis", {
                "determination": decision.determination,
                "confidence": decision.genuine_alert_confidence,
            })

        return decision

    async def astream_analyze_request(
        self,
        request: AnalysisRequest,
        task_id: str,
    ) -> AsyncIterator[StreamEvent]:
        """Analyze an alert with streaming events using proactive info flow.

        This async generator yields StreamEvent objects as the analysis progresses,
        enabling real-time progress updates to the client.

        Args:
            request: AnalysisRequest with alert_xml, agent_type, and tool_data
            task_id: Task ID for event correlation

        Yields:
            StreamEvent objects for each progress update

        Raises:
            MissingToolDataError: If required tool data is not provided
            Exception: If analysis fails
        """
        start_time = datetime.now(timezone.utc)
        event_mapper = EventMapper(task_id=task_id, agent_name="wash_trade")

        self.logger.info("=" * 60)
        self.logger.info("Starting streaming deterministic wash trade analysis")
        self.logger.info(f"Task ID: {task_id}")
        self.logger.info("=" * 60)

        # Emit analysis started event
        yield event_mapper.create_analysis_started_event("proactive_request")

        insights: Dict[str, str] = {}

        try:
            # Execute tools in fixed order
            for tool_name in self.TOOL_ORDER:
                tool_data_key = self._get_tool_data_key(tool_name)

                self.logger.info(f"Executing tool: {tool_name}")

                # Get tool data from request
                tool_input = request.tool_data.get(tool_data_key)
                if tool_input is None:
                    error_event = event_mapper.create_error_event(
                        f"Missing tool data: {tool_data_key}",
                        stage="tool_execution",
                        fatal=True,
                    )
                    yield error_event
                    raise MissingToolDataError(tool_data_key)

                # Emit tool started event
                yield event_mapper.create_tool_started_event(tool_name)

                # Get tool instance and execute
                tool = self.tool_instances.get(tool_name)
                if tool is None:
                    raise ValueError(f"Unknown tool: {tool_name}")

                try:
                    insight = tool.execute(
                        data=tool_input.data,
                        format=tool_input.format,
                    )
                    insights[tool_name] = insight

                    # Emit tool completed event
                    yield event_mapper.create_tool_completed_event(
                        tool_name,
                        summary=insight[:200] + "..." if len(insight) > 200 else insight
                    )

                except Exception as e:
                    self.logger.error(f"Tool {tool_name} failed: {e}")
                    yield event_mapper.create_error_event(
                        str(e),
                        stage=f"tool_{tool_name}",
                        fatal=True,
                    )
                    raise

            # Emit evaluation started event
            yield event_mapper.create_evaluation_started_event()

            # Synthesize final decision
            decision = self._synthesize(insights)

            # Calculate processing time
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Write outputs
            self._write_decision(decision)
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
                f"Streaming wash trade analysis completed in {elapsed:.2f}s: {decision.determination}"
            )

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(f"Streaming analysis failed after {elapsed:.2f}s: {e}", exc_info=True)
            yield event_mapper.create_error_event(
                str(e),
                stage="analysis",
                fatal=True,
            )
            raise

    def _synthesize(self, insights: Dict[str, str]) -> WashTradeDecision:
        """Synthesize tool insights into a final decision.

        This is the ONLY LLM reasoning step in the deterministic workflow.

        Args:
            insights: Dict mapping tool names to their insight strings

        Returns:
            WashTradeDecision with determination and reasoning

        Raises:
            ValueError: If LLM fails to produce valid decision
        """
        self.logger.info("Synthesizing final wash trade decision from tool insights")

        # Build context from all tool insights
        insights_text = "\n\n".join([
            f"## {tool_name.replace('_', ' ').title()} Analysis\n{insight}"
            for tool_name, insight in insights.items()
        ])

        # Build system prompt with few-shot examples
        examples_text = None
        if self.few_shot_examples:
            examples_text = self.few_shot_examples.get_examples_text()

        system_prompt = get_wash_trade_system_prompt(examples_text)
        decision_prompt = get_wash_trade_final_decision_prompt()

        # Construct messages for LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"""Based on the following tool analyses, provide your final wash trade determination.

{insights_text}

{decision_prompt}"""),
        ]

        # Get structured response
        llm_structured = self.llm.with_structured_output(WashTradeDecision)
        decision = llm_structured.invoke(messages)

        # Fail-fast if decision is None
        if decision is None:
            self._log_failed_synthesis(insights, messages)
            raise ValueError(
                "LLM returned None for structured decision. "
                "Check resources/debug/ for response details."
            )

        self.logger.info(
            f"Decision synthesized: {decision.determination} "
            f"(genuine: {decision.genuine_alert_confidence}%, "
            f"false_positive: {decision.false_positive_confidence}%)"
        )

        return decision

    def _log_failed_synthesis(
        self,
        insights: Dict[str, str],
        messages: List[Any],
    ) -> None:
        """Log failed synthesis to debug file for investigation.

        Args:
            insights: Tool insights that were used
            messages: Messages sent to LLM
        """
        debug_dir = Path("resources/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        debug_file = debug_dir / f"wash_trade_failed_synthesis_{timestamp}.json"

        debug_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error_reason": "LLM returned None decision during synthesis",
            "insights_summary": {
                name: insight[:500] for name, insight in insights.items()
            },
            "messages_count": len(messages),
        }

        debug_file.write_text(json.dumps(debug_data, indent=2, default=str))
        self.logger.error(f"Failed synthesis logged to {debug_file.absolute()}")

    # =========================================================================
    # Legacy methods for backward compatibility with file-based loading
    # These will be deprecated once all consumers migrate to analyze_request()
    # =========================================================================

    def analyze(self, alert_file_path: Path) -> WashTradeDecision:
        """Legacy method: Analyze an alert by loading data from files.

        DEPRECATED: Use analyze_request() with AnalysisRequest instead.

        Args:
            alert_file_path: Path to the alert XML file

        Returns:
            WashTradeDecision with the determination and reasoning
        """
        self.logger.warning(
            "analyze() is deprecated. Use analyze_request() with AnalysisRequest instead."
        )

        # For backward compatibility, we need to load data from files
        from alerts.mock.bigdata_simulator import BigDataSimulator

        simulator = BigDataSimulator(str(self.data_dir))
        request = simulator.create_request(str(alert_file_path))

        decision = self.analyze_request(request)

        # Also write HTML report for legacy compatibility
        self._write_html_report(decision, alert_file_path)

        return decision

    async def astream_analyze(
        self,
        alert_file_path: Path,
        task_id: str,
    ) -> AsyncIterator[StreamEvent]:
        """Legacy method: Analyze an alert with streaming by loading from files.

        DEPRECATED: Use astream_analyze_request() with AnalysisRequest instead.

        Args:
            alert_file_path: Path to the alert XML file
            task_id: Task ID for event correlation

        Yields:
            StreamEvent objects for each progress update
        """
        self.logger.warning(
            "astream_analyze() is deprecated. Use astream_analyze_request() instead."
        )

        # For backward compatibility, load data from files
        from alerts.mock.bigdata_simulator import BigDataSimulator

        simulator = BigDataSimulator(str(self.data_dir))
        request = simulator.create_request(str(alert_file_path))

        async for event in self.astream_analyze_request(request, task_id):
            yield event

    def _write_decision(self, decision: WashTradeDecision) -> Path:
        """Write decision to JSON file.

        Args:
            decision: WashTradeDecision to write

        Returns:
            Path to written file
        """
        output_file = self.output_dir / f"wash_trade_decision_{decision.alert_id}.json"

        self.logger.info(f"Writing decision to {output_file}")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(decision.model_dump_json(indent=2))

        return output_file

    def _write_html_report(self, decision: WashTradeDecision, alert_file_path: Path) -> Path:
        """Generate and write HTML report with SVG network visualization.

        Args:
            decision: WashTradeDecision to render
            alert_file_path: Path to the original alert XML file

        Returns:
            Path to written HTML file
        """
        output_file = self.output_dir / f"wash_trade_decision_{decision.alert_id}.html"

        self.logger.info(f"Generating HTML report: {output_file}")

        try:
            generator = WashTradeHTMLReportGenerator.from_xml_file(
                alert_xml_path=alert_file_path,
                decision=decision,
            )
            html_content = generator.generate()

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html_content)

            self.logger.info(f"HTML report written to {output_file}")
            return output_file

        except Exception as e:
            self.logger.error(f"Failed to generate HTML report: {e}", exc_info=True)
            raise

    def _write_audit_log(self, decision: WashTradeDecision, processing_time: float) -> None:
        """Append to audit log.

        Args:
            decision: WashTradeDecision to log
            processing_time: Processing time in seconds
        """
        audit_file = self.output_dir / "audit_log.jsonl"

        self.logger.info(f"Appending to audit log: {audit_file}")

        audit_entry = decision.to_audit_entry()
        audit_entry["processing_time_seconds"] = round(processing_time, 2)

        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")

    def get_tool_stats(self) -> dict:
        """Get statistics about tool usage.

        Returns:
            Dictionary with tool statistics
        """
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": "wash_trade",
            "tools": [t.get_stats() for t in self.tool_instances.values()]
        }
