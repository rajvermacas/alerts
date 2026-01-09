"""Deterministic agent for Insider Trading Alert Analysis.

This module implements the insider trading analyzer agent that orchestrates
tool calls in a fixed order and produces the final determination for insider
trading alerts.

Supports both synchronous analyze() and async astream_analyze() for real-time streaming.

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                    AnalysisRequest                       │
    │  (alert_xml, agent_type, tool_data: Dict[str, ToolInput])│
    └─────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────┐
    │              InsiderTradingAnalyzerAgent                 │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │  TOOL_ORDER = [                                     │ │
    │  │    "alert_reader",                                  │ │
    │  │    "market_news",                                   │ │
    │  │    "market_data",                                   │ │
    │  │    "trader_profile",                                │ │
    │  │    "trader_history",                                │ │
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
                     InsiderTradingDecision
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from alerts.a2a.event_mapper import EventMapper, StreamEvent
from alerts.exceptions import MissingToolDataError
from alerts.models.insider_trading import InsiderTradingDecision
from alerts.models.request import AnalysisRequest, ToolInput
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


class InsiderTradingAnalyzerAgent:
    """Deterministic agent for analyzing SMARTS insider trading alerts.

    This agent uses a fixed tool order approach to gather evidence and
    produce a structured determination for insider trading alerts.
    No LLM routing is used - tools are executed in a predetermined order.

    Attributes:
        llm: LangChain LLM instance
        data_dir: Path to data directory
        output_dir: Path to output directory
        tool_instances: Dict mapping tool names to instances
    """

    # Fixed order of tool execution - no LLM routing needed
    TOOL_ORDER: List[str] = [
        "read_alert",
        "query_market_news",
        "query_market_data",
        "query_trader_profile",
        "query_trader_history",
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

        self.logger.info("Initializing InsiderTradingAnalyzerAgent (Deterministic)")
        self.logger.info(f"Data directory: {data_dir}")
        self.logger.info(f"Output directory: {output_dir}")

        # Load few-shot examples
        examples_path = data_dir / "few_shot_examples.json"
        self.few_shot_examples = load_few_shot_examples(examples_path)
        if not self.few_shot_examples:
            raise FileNotFoundError(f"Few-shot examples not found: {examples_path}")

        # Initialize tool instances as a dict for name-based lookup
        self.tool_instances = self._create_tool_instances()
        self.logger.info(f"Created {len(self.tool_instances)} tool instances")
        self.logger.info(f"Tool execution order: {self.TOOL_ORDER}")

    def _create_tool_instances(self) -> Dict[str, Any]:
        """Create instances of all analysis tools.

        Returns:
            Dict mapping tool names to tool instances
        """
        tools = [
            # Common tools
            AlertReaderTool(self.llm, self.data_dir),
            TraderProfileTool(self.llm, self.data_dir),
            MarketDataTool(self.llm, self.data_dir),
            # Insider trading specific tools
            TraderHistoryTool(self.llm, self.data_dir),
            MarketNewsTool(self.llm, self.data_dir),
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
            "query_market_news": "market_news",
            "query_market_data": "market_data",
            "query_trader_profile": "trader_profile",
            "query_trader_history": "trader_history",
        }
        return tool_key_map.get(tool_name, tool_name)

    def _build_context_params(self, context: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        """Build per-tool context parameters from alert context.

        Maps the extracted alert context (symbol, trader_id, dates) to the
        specific parameters each tool requires in its _build_interpretation_prompt.

        Args:
            context: Dict with keys: trader_id, symbol, trade_date, start_date, end_date

        Returns:
            Dict mapping tool names to their required kwargs
        """
        return {
            "query_market_news": {
                "symbol": context["symbol"],
                "start_date": context["start_date"],
                "end_date": context["end_date"],
            },
            "query_market_data": {
                "symbol": context["symbol"],
                "start_date": context["start_date"],
                "end_date": context["end_date"],
            },
            "query_trader_profile": {
                "trader_id": context["trader_id"],
            },
            "query_trader_history": {
                "trader_id": context["trader_id"],
                "symbol": context["symbol"],
                "trade_date": context["trade_date"],
            },
        }

    def analyze_request(
        self,
        request: AnalysisRequest,
        event_callback: Optional[Callable[[str, str, Optional[Dict]], None]] = None,
    ) -> InsiderTradingDecision:
        """Analyze an alert using the proactive info flow pattern.

        This method uses data injected via AnalysisRequest instead of
        loading data from files. It extracts context parameters from the
        alert XML and passes them to each tool for proper prompt building.

        Args:
            request: AnalysisRequest with alert_xml, agent_type, and tool_data
            event_callback: Optional callback for emitting events
                           Signature: (event_type, tool_name, data) -> None

        Returns:
            InsiderTradingDecision with the determination and reasoning

        Raises:
            MissingToolDataError: If required tool data is not provided
            Exception: If analysis fails
        """
        start_time = datetime.now(timezone.utc)

        self.logger.info("=" * 60)
        self.logger.info("Starting deterministic insider trading analysis")
        self.logger.info(f"Agent type: {request.agent_type}")
        self.logger.info(f"Tool data keys: {list(request.tool_data.keys())}")
        self.logger.info("=" * 60)

        insights: Dict[str, str] = {}

        # Step 1: Execute alert_reader first to extract context parameters
        alert_tool_name = "read_alert"
        alert_data_key = self._get_tool_data_key(alert_tool_name)

        self.logger.info(f"Step 1: Executing {alert_tool_name} and extracting context")

        alert_input = request.tool_data.get(alert_data_key)
        if alert_input is None:
            raise MissingToolDataError(alert_data_key)

        # Emit tool started event for alert reader
        if event_callback:
            event_callback("tool_started", alert_tool_name, None)

        alert_reader = self.tool_instances.get(alert_tool_name)
        if alert_reader is None:
            raise ValueError(f"Unknown tool: {alert_tool_name}")

        try:
            alert_insight = alert_reader.execute(
                data=alert_input.data,
                format=alert_input.format,
            )
            insights[alert_tool_name] = alert_insight
            self.logger.info(f"Tool {alert_tool_name} completed successfully")

            if event_callback:
                event_callback("tool_completed", alert_tool_name, {"insight_length": len(alert_insight)})

        except Exception as e:
            self.logger.error(f"Tool {alert_tool_name} failed: {e}")
            if event_callback:
                event_callback("tool_error", alert_tool_name, {"error": str(e)})
            raise

        # Step 2: Extract context parameters from alert XML for other tools
        self.logger.info("Step 2: Extracting context parameters from alert XML")
        context = AlertReaderTool.parse_alert_context(alert_input.data)
        context_params = self._build_context_params(context)
        self.logger.info(f"Extracted context: symbol={context['symbol']}, trader_id={context['trader_id']}")

        # Step 3: Execute remaining tools with context parameters
        self.logger.info("Step 3: Executing remaining tools with context")
        for tool_name in self.TOOL_ORDER[1:]:  # Skip alert_reader (already executed)
            tool_data_key = self._get_tool_data_key(tool_name)

            self.logger.info(f"Executing tool: {tool_name} (data key: {tool_data_key})")

            # Get tool data from request
            tool_input = request.tool_data.get(tool_data_key)
            if tool_input is None:
                raise MissingToolDataError(tool_data_key)

            # Emit tool started event
            if event_callback:
                event_callback("tool_started", tool_name, None)

            # Get tool instance and execute with injected data + context params
            tool = self.tool_instances.get(tool_name)
            if tool is None:
                raise ValueError(f"Unknown tool: {tool_name}")

            # Get context params for this tool (empty dict if not found)
            tool_context = context_params.get(tool_name, {})
            self.logger.debug(f"Tool {tool_name} context params: {tool_context}")

            try:
                insight = tool.execute(
                    data=tool_input.data,
                    format=tool_input.format,
                    **tool_context,  # Pass context parameters to tool
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
        self.logger.info(f"Analysis completed in {elapsed:.2f}s")

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
        enabling real-time progress updates to the client. It extracts context
        parameters from the alert XML and passes them to each tool.

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
        event_mapper = EventMapper(task_id=task_id, agent_name="insider_trading")

        self.logger.info("=" * 60)
        self.logger.info("Starting streaming deterministic insider trading analysis")
        self.logger.info(f"Task ID: {task_id}")
        self.logger.info("=" * 60)

        # Emit analysis started event
        yield event_mapper.create_analysis_started_event("proactive_request")

        insights: Dict[str, str] = {}
        context_params: Dict[str, Dict[str, str]] = {}

        try:
            # Step 1: Execute alert_reader first and extract context
            alert_tool_name = "read_alert"
            alert_data_key = self._get_tool_data_key(alert_tool_name)

            self.logger.info(f"Step 1: Executing {alert_tool_name} and extracting context")

            alert_input = request.tool_data.get(alert_data_key)
            if alert_input is None:
                error_event = event_mapper.create_error_event(
                    f"Missing tool data: {alert_data_key}",
                    stage="tool_execution",
                    fatal=True,
                )
                yield error_event
                raise MissingToolDataError(alert_data_key)

            yield event_mapper.create_tool_started_event(alert_tool_name)

            alert_reader = self.tool_instances.get(alert_tool_name)
            if alert_reader is None:
                raise ValueError(f"Unknown tool: {alert_tool_name}")

            try:
                alert_insight = alert_reader.execute(
                    data=alert_input.data,
                    format=alert_input.format,
                )
                insights[alert_tool_name] = alert_insight

                yield event_mapper.create_tool_completed_event(
                    alert_tool_name,
                    summary=alert_insight[:200] + "..." if len(alert_insight) > 200 else alert_insight
                )

            except Exception as e:
                self.logger.error(f"Tool {alert_tool_name} failed: {e}")
                yield event_mapper.create_error_event(
                    str(e),
                    stage=f"tool_{alert_tool_name}",
                    fatal=True,
                )
                raise

            # Step 2: Extract context parameters from alert XML
            self.logger.info("Step 2: Extracting context parameters from alert XML")
            context = AlertReaderTool.parse_alert_context(alert_input.data)
            context_params = self._build_context_params(context)
            self.logger.info(f"Extracted context: symbol={context['symbol']}, trader_id={context['trader_id']}")

            # Step 3: Execute remaining tools with context parameters
            self.logger.info("Step 3: Executing remaining tools with context")
            for tool_name in self.TOOL_ORDER[1:]:  # Skip alert_reader (already executed)
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

                # Get context params for this tool
                tool_context = context_params.get(tool_name, {})
                self.logger.debug(f"Tool {tool_name} context params: {tool_context}")

                try:
                    insight = tool.execute(
                        data=tool_input.data,
                        format=tool_input.format,
                        **tool_context,  # Pass context parameters to tool
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
                f"Streaming analysis completed in {elapsed:.2f}s: {decision.determination}"
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

    def _synthesize(self, insights: Dict[str, str]) -> InsiderTradingDecision:
        """Synthesize tool insights into a final decision.

        This is the ONLY LLM reasoning step in the deterministic workflow.

        Args:
            insights: Dict mapping tool names to their insight strings

        Returns:
            InsiderTradingDecision with determination and reasoning

        Raises:
            ValueError: If LLM fails to produce valid decision
        """
        self.logger.info("Synthesizing final decision from tool insights")

        # Build context from all tool insights
        insights_text = "\n\n".join([
            f"## {tool_name.replace('_', ' ').title()} Analysis\n{insight}"
            for tool_name, insight in insights.items()
        ])

        # Build system prompt with few-shot examples
        system_prompt = get_system_prompt(self.few_shot_examples)
        decision_prompt = get_final_decision_prompt()

        # Construct messages for LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"""Based on the following tool analyses, provide your final insider trading determination.

{insights_text}

{decision_prompt}"""),
        ]

        # Get structured response
        llm_structured = self.llm.with_structured_output(InsiderTradingDecision)
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
        debug_file = debug_dir / f"insider_trading_failed_synthesis_{timestamp}.json"

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

    def analyze(self, alert_file_path: Path) -> InsiderTradingDecision:
        """Legacy method: Analyze an alert by loading data from files.

        DEPRECATED: Use analyze_request() with AnalysisRequest instead.

        Args:
            alert_file_path: Path to the alert XML file

        Returns:
            InsiderTradingDecision with the determination and reasoning
        """
        self.logger.warning(
            "analyze() is deprecated. Use analyze_request() with AnalysisRequest instead."
        )

        # For backward compatibility, we need to load data from files
        # This should be removed once all consumers migrate
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

        # Write HTML report for legacy compatibility
        # Note: We need to get the decision from somewhere
        # This is a limitation of the streaming interface

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

    def _write_html_report(self, decision: InsiderTradingDecision, alert_file_path: Path) -> Path:
        """Write decision to HTML report.

        Args:
            decision: InsiderTradingDecision to write
            alert_file_path: Path to the original alert XML file

        Returns:
            Path to written HTML file
        """
        output_file = self.output_dir / f"decision_{decision.alert_id}.html"

        self.logger.info(f"Writing HTML report to {output_file}")

        try:
            generator = HTMLReportGenerator.from_xml_file(alert_file_path, decision)
            html_content = generator.generate()

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html_content)

            self.logger.info(f"HTML report written successfully: {output_file}")
            return output_file

        except Exception as e:
            self.logger.error(f"Failed to write HTML report: {e}", exc_info=True)
            raise

    def _write_audit_log(self, decision: InsiderTradingDecision, processing_time: float) -> None:
        """Append to audit log.

        Args:
            decision: InsiderTradingDecision to log
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
            "tools": [t.get_stats() for t in self.tool_instances.values()]
        }


# Backward compatibility alias
AlertAnalyzerAgent = InsiderTradingAnalyzerAgent
