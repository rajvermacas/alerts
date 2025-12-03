"""LangGraph agent for Wash Trade Alert Analysis.

This module implements the wash trade analyzer agent that orchestrates
tool calls and produces the final determination for wash trade alerts.

Supports both synchronous analyze() and async astream_analyze() for real-time streaming.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from alerts.a2a.event_mapper import EventMapper, StreamEvent, create_stream_writer_for_mapper

from alerts.models.wash_trade import (
    WashTradeDecision,
    RelationshipNetwork,
    RelationshipNode,
    RelationshipEdge,
    TimingPattern,
    CounterpartyPattern,
    TradeFlow,
    HistoricalPatternSummary,
)
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
from alerts.reports.wash_trade_report import WashTradeHTMLReportGenerator

logger = logging.getLogger(__name__)


# Tool argument schemas
class ReadAlertArgs(BaseModel):
    """Arguments for the read_alert tool."""
    alert_file_path: str = Field(
        description="Path to the alert XML file to read (e.g., 'test_data/alerts/wash_trade/wash_genuine.xml')"
    )


class QueryAccountRelationshipsArgs(BaseModel):
    """Arguments for the account_relationships tool."""
    account_id: str = Field(
        description="Account ID to look up beneficial ownership and relationships for"
    )


class QueryRelatedAccountsHistoryArgs(BaseModel):
    """Arguments for the related_accounts_history tool."""
    account_ids: str = Field(
        description="Comma-separated list of account IDs (e.g., 'ACC-001,ACC-002')"
    )
    symbol: Optional[str] = Field(
        default=None,
        description="Optional symbol to filter trades"
    )
    time_window: str = Field(
        default="30d",
        description="Time window for analysis (e.g., '30d', '7d')"
    )


class QueryTradeTimingArgs(BaseModel):
    """Arguments for the trade_timing tool."""
    trade1_timestamp: str = Field(
        description="Timestamp of first trade (e.g., '14:32:15.123' or '2024-01-15 14:32:15.123')"
    )
    trade2_timestamp: str = Field(
        description="Timestamp of second trade (e.g., '14:32:15.625' or '2024-01-15 14:32:15.625')"
    )
    symbol: Optional[str] = Field(
        default=None,
        description="Trading symbol for context"
    )
    trade_quantity: Optional[str] = Field(
        default=None,
        description="Trade quantity for execution time benchmarking"
    )


class QueryCounterpartyAnalysisArgs(BaseModel):
    """Arguments for the counterparty_analysis tool."""
    trades: str = Field(
        description=(
            "JSON string of trades with format: "
            '[{"account_id": "ACC-001", "side": "BUY", "quantity": 10000, '
            '"price": 150.0, "counterparty_account": "ACC-002", "symbol": "AAPL"}, ...]'
        )
    )


class QueryMarketDataArgs(BaseModel):
    """Arguments for the query_market_data tool."""
    symbol: str = Field(description="Stock symbol to query")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: str = Field(description="End date in YYYY-MM-DD format")


class WashTradeAnalyzerAgent:
    """LangGraph agent for analyzing SMARTS wash trade alerts.

    This agent uses a multi-tool approach to gather evidence and
    produce a structured determination for wash trade alerts.

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
        tool_instances: List of tool class instances
        tools: List of LangChain tools
        graph: Compiled LangGraph workflow
    """

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

        self.logger.info("Initializing WashTradeAnalyzerAgent")
        self.logger.info(f"Data directory: {data_dir}")
        self.logger.info(f"Output directory: {output_dir}")

        # Load few-shot examples (optional - may not exist yet)
        self.few_shot_examples = load_wash_trade_few_shot_examples(str(data_dir))
        if self.few_shot_examples:
            self.logger.info(f"Loaded {len(self.few_shot_examples.examples)} few-shot examples")
        else:
            self.logger.warning("No wash trade few-shot examples loaded - using base prompts")

        # Initialize tool instances
        self.tool_instances = self._create_tool_instances()
        self.logger.info(f"Created {len(self.tool_instances)} tool instances")

        # Convert to LangChain tools
        self.tools = self._create_langchain_tools()
        self.logger.info(f"Registered {len(self.tools)} LangChain tools")

        # Bind tools to LLM
        self.llm_with_tools = llm.bind_tools(self.tools)

        # Build the graph
        self.graph = self._build_graph()
        self.logger.info("LangGraph workflow compiled successfully")

    def _create_tool_instances(self) -> list:
        """Create instances of all analysis tools.

        Returns:
            List of tool instances
        """
        data_dir_str = str(self.data_dir)

        return [
            # Common tools
            AlertReaderTool(self.llm, self.data_dir),
            MarketDataTool(self.llm, self.data_dir),
            # Wash trade specific tools
            AccountRelationshipsTool(self.llm, data_dir_str),
            RelatedAccountsHistoryTool(self.llm, data_dir_str),
            TradeTimingTool(self.llm, data_dir_str),
            CounterpartyAnalysisTool(self.llm, data_dir_str),
        ]

    def _create_langchain_tools(self, config: Optional[Dict[str, Any]] = None) -> list:
        """Convert tool instances to LangChain tools with proper schemas.

        Args:
            config: Optional config dict to pass to tools (e.g., with stream_writer)

        Returns:
            List of LangChain tools
        """
        # Map tool names to their argument schemas
        schema_map = {
            "read_alert": ReadAlertArgs,
            "account_relationships": QueryAccountRelationshipsArgs,
            "related_accounts_history": QueryRelatedAccountsHistoryArgs,
            "trade_timing": QueryTradeTimingArgs,
            "counterparty_analysis": QueryCounterpartyAnalysisArgs,
            "query_market_data": QueryMarketDataArgs,
        }

        langchain_tools = []

        for tool_instance in self.tool_instances:
            # Get the schema for this tool
            args_schema = schema_map.get(tool_instance.name)
            if not args_schema:
                self.logger.warning(f"No schema defined for tool: {tool_instance.name}, skipping")
                continue

            # Create a wrapper function that captures the instance and config
            def make_tool_func(instance, tool_config):
                def tool_func(**kwargs) -> str:
                    return instance(config=tool_config, **kwargs)
                return tool_func

            # Create StructuredTool with explicit schema
            lc_tool = StructuredTool.from_function(
                func=make_tool_func(tool_instance, config),
                name=tool_instance.name,
                description=tool_instance.description,
                args_schema=args_schema,
            )
            langchain_tools.append(lc_tool)

        return langchain_tools

    def _build_graph(self) -> Any:
        """Build the LangGraph workflow.

        Returns:
            Compiled StateGraph
        """
        self.logger.debug("Building LangGraph workflow")

        builder = StateGraph(MessagesState)

        # Add nodes
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_node("respond", self._respond_node)

        # Add edges
        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "tools": "tools",
                "respond": "respond",
            }
        )
        builder.add_edge("tools", "agent")
        builder.add_edge("respond", END)

        return builder.compile()

    def _build_streaming_graph(self, streaming_tools: list, streaming_llm_with_tools: Any) -> Any:
        """Build a LangGraph workflow with streaming-enabled tools.

        This method creates a new graph instance that uses tools configured
        with a stream_writer callback, enabling real-time event emission
        during tool execution.

        Args:
            streaming_tools: List of LangChain tools with stream_writer config
            streaming_llm_with_tools: LLM instance bound to streaming tools

        Returns:
            Compiled StateGraph with streaming tools
        """
        self.logger.debug("Building streaming LangGraph workflow")

        builder = StateGraph(MessagesState)

        # Create a streaming agent node that uses the streaming LLM
        def streaming_agent_node(state: MessagesState) -> dict:
            """Agent node using streaming-enabled LLM with tools."""
            self.logger.info(f"Streaming agent node: processing {len(state['messages'])} messages")

            # Build system prompt with few-shot examples
            examples_text = None
            if self.few_shot_examples:
                examples_text = self.few_shot_examples.get_examples_text()

            system_prompt = get_wash_trade_system_prompt(examples_text)
            messages = [SystemMessage(content=system_prompt)] + state["messages"]

            # Invoke streaming LLM with tools
            response = streaming_llm_with_tools.invoke(messages)

            # Log tool calls if any
            if hasattr(response, 'tool_calls') and response.tool_calls:
                tool_names = [tc.get("name", "unknown") for tc in response.tool_calls]
                self.logger.info(f"Streaming agent requesting tools: {tool_names}")

            return {"messages": [response]}

        # Add nodes - use streaming tools in ToolNode
        builder.add_node("agent", streaming_agent_node)
        builder.add_node("tools", ToolNode(streaming_tools))
        builder.add_node("respond", self._respond_node)

        # Add edges (same as non-streaming graph)
        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "tools": "tools",
                "respond": "respond",
            }
        )
        builder.add_edge("tools", "agent")
        builder.add_edge("respond", END)

        return builder.compile()

    def _agent_node(self, state: MessagesState) -> dict:
        """Main agent node that decides what to do.

        Args:
            state: Current graph state with messages

        Returns:
            Updated state with agent response
        """
        self.logger.info(f"Agent node: processing {len(state['messages'])} messages")

        # Build system prompt with few-shot examples
        examples_text = None
        if self.few_shot_examples:
            examples_text = self.few_shot_examples.get_examples_text()

        system_prompt = get_wash_trade_system_prompt(examples_text)

        messages = [SystemMessage(content=system_prompt)] + state["messages"]

        # Invoke LLM with tools
        response = self.llm_with_tools.invoke(messages)

        # Log tool calls if any
        if hasattr(response, 'tool_calls') and response.tool_calls:
            tool_names = [tc.get("name", "unknown") for tc in response.tool_calls]
            self.logger.info(f"Agent requesting tools: {tool_names}")

        return {"messages": [response]}

    def _should_continue(self, state: MessagesState) -> Literal["tools", "respond"]:
        """Decide whether to continue with tools or generate response.

        Args:
            state: Current graph state

        Returns:
            Next node name ("tools" or "respond")
        """
        last_message = state["messages"][-1]

        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            self.logger.debug("Routing to tools node")
            return "tools"

        self.logger.debug("Routing to respond node")
        return "respond"

    def _respond_node(self, state: MessagesState) -> dict:
        """Generate final structured response.

        Args:
            state: Current graph state with all messages

        Returns:
            Updated state with final response
        """
        self.logger.info("Respond node: generating structured decision")

        try:
            # Create LLM with structured output
            llm_structured = self.llm.with_structured_output(WashTradeDecision)

            # Build final decision prompt
            decision_prompt = get_wash_trade_final_decision_prompt()

            # Add decision prompt to conversation
            messages = state["messages"] + [
                HumanMessage(content=decision_prompt)
            ]

            # Get structured response
            decision = llm_structured.invoke(messages)

            self.logger.info(
                f"Decision generated: {decision.determination} "
                f"(genuine: {decision.genuine_alert_confidence}%, "
                f"false_positive: {decision.false_positive_confidence}%)"
            )

            # Return as JSON message
            return {
                "messages": [AIMessage(content=decision.model_dump_json(indent=2))]
            }

        except Exception as e:
            self.logger.error(f"Failed to generate structured decision: {e}", exc_info=True)

            # Create fallback decision
            fallback = self._create_fallback_decision(str(e))

            return {
                "messages": [AIMessage(content=fallback.model_dump_json(indent=2))]
            }

    def _create_fallback_decision(self, error_message: str) -> WashTradeDecision:
        """Create a fallback decision when analysis fails.

        Args:
            error_message: Error message to include

        Returns:
            WashTradeDecision with fallback values
        """
        return WashTradeDecision(
            alert_id="UNKNOWN",
            determination="NEEDS_HUMAN_REVIEW",
            genuine_alert_confidence=50,
            false_positive_confidence=50,
            key_findings=["Error occurred during analysis"],
            favorable_indicators=["Unable to determine"],
            risk_mitigating_factors=["Unable to determine"],
            relationship_network=RelationshipNetwork(
                nodes=[
                    RelationshipNode(
                        account_id="UNKNOWN",
                        beneficial_owner_id="UNKNOWN",
                        beneficial_owner_name="Unknown",
                        relationship_type="direct",
                        is_flagged=True,
                    )
                ],
                edges=[
                    RelationshipEdge(
                        from_account="UNKNOWN",
                        to_account="UNKNOWN",
                        edge_type="trade",
                        is_suspicious=True,
                    )
                ],
                pattern_type="NO_PATTERN",
                pattern_confidence=0,
                pattern_description="Analysis failed - unable to determine pattern",
            ),
            timing_patterns=TimingPattern(
                time_delta_ms=0,
                time_delta_description="Unknown",
                market_phase="unknown",
                liquidity_assessment="medium",
                is_pre_arranged=False,
                pre_arrangement_confidence=0,
                timing_analysis="Analysis failed - unable to assess timing",
            ),
            counterparty_pattern=CounterpartyPattern(
                trade_flow=[
                    TradeFlow(
                        sequence_number=1,
                        account_id="UNKNOWN",
                        side="BUY",
                        quantity=0,
                        price=0.0,
                        timestamp="Unknown",
                    ),
                    TradeFlow(
                        sequence_number=2,
                        account_id="UNKNOWN",
                        side="SELL",
                        quantity=0,
                        price=0.0,
                        timestamp="Unknown",
                    ),
                ],
                is_circular=False,
                is_offsetting=False,
                same_beneficial_owner=False,
                economic_purpose_identified=False,
            ),
            historical_patterns=HistoricalPatternSummary(
                pattern_count=0,
                time_window_days=30,
                average_frequency="Unknown",
                pattern_trend="new",
                historical_analysis="Analysis failed - unable to assess history",
            ),
            volume_impact_percentage=0.0,
            beneficial_ownership_match=False,
            economic_purpose_identified=False,
            regulatory_flags=[],
            reasoning_narrative=f"Analysis failed with error: {error_message}. Manual review required.",
            similar_precedent="Unable to determine due to error",
            recommended_action="REQUEST_MORE_DATA",
            data_gaps=["Complete re-analysis required"],
        )

    def analyze(self, alert_file_path: Path) -> WashTradeDecision:
        """Analyze an alert and produce a determination.

        Args:
            alert_file_path: Path to the alert XML file

        Returns:
            WashTradeDecision with the determination and reasoning

        Raises:
            FileNotFoundError: If alert file doesn't exist
            Exception: If analysis fails
        """
        start_time = datetime.now(timezone.utc)

        self.logger.info("=" * 60)
        self.logger.info(f"Starting wash trade analysis of alert: {alert_file_path}")
        self.logger.info("=" * 60)

        if not alert_file_path.exists():
            raise FileNotFoundError(f"Alert file not found: {alert_file_path}")

        # Store alert file path for HTML report generation
        self._current_alert_path = alert_file_path

        # Create initial message with alert file path
        initial_message = HumanMessage(
            content=f"""Please analyze the following SMARTS alert for potential wash trading.

Alert file path: {alert_file_path}

Start by reading the alert, then systematically gather evidence using all available tools:
1. First, read the alert to understand the flagged trades
2. Check account relationships to find beneficial ownership
3. Query related accounts history for trading patterns
4. Analyze trade timing for pre-arrangement indicators
5. Perform counterparty analysis to detect circular patterns
6. Check market data for context

After collecting all evidence, provide your determination with detailed reasoning."""
        )

        # Run the graph
        self.logger.info("Invoking LangGraph workflow")

        try:
            result = self.graph.invoke(
                {"messages": [initial_message]},
                {"recursion_limit": 50}  # Allow many tool calls
            )

            # Extract the final decision from the last message
            last_message = result["messages"][-1]

            if isinstance(last_message.content, str) and last_message.content.startswith("{"):
                try:
                    data = json.loads(last_message.content)
                    decision = WashTradeDecision(**data)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse decision JSON: {e}")
                    raise
            else:
                self.logger.error("Last message is not valid JSON")
                raise ValueError("Agent did not produce valid structured output")

            # Calculate processing time
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.info(f"Wash trade analysis completed in {elapsed:.2f}s")

            # Write outputs
            self._write_decision(decision)
            self._write_html_report(decision, alert_file_path)
            self._write_audit_log(decision, elapsed)

            return decision

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(f"Wash trade analysis failed after {elapsed:.2f}s: {e}", exc_info=True)
            raise

    async def astream_analyze(
        self,
        alert_file_path: Path,
        task_id: str,
    ) -> AsyncIterator[StreamEvent]:
        """Analyze an alert with streaming events.

        This async generator yields StreamEvent objects as the analysis progresses,
        enabling real-time progress updates to the client.

        Args:
            alert_file_path: Path to the alert XML file
            task_id: Task ID for event correlation

        Yields:
            StreamEvent objects for each progress update

        Raises:
            FileNotFoundError: If alert file doesn't exist
            Exception: If analysis fails
        """
        start_time = datetime.now(timezone.utc)
        event_mapper = EventMapper(task_id=task_id, agent_name="wash_trade")
        collected_events: List[StreamEvent] = []

        self.logger.info("=" * 60)
        self.logger.info(f"Starting streaming wash trade analysis: {alert_file_path}")
        self.logger.info("=" * 60)

        if not alert_file_path.exists():
            error_event = event_mapper.create_error_event(
                f"Alert file not found: {alert_file_path}",
                stage="initialization",
                fatal=True,
            )
            yield error_event
            raise FileNotFoundError(f"Alert file not found: {alert_file_path}")

        # Emit analysis started event
        yield event_mapper.create_analysis_started_event(str(alert_file_path))

        # Create stream writer for tools
        stream_writer = create_stream_writer_for_mapper(event_mapper, collected_events)

        # Create tools with streaming config
        streaming_config = {"stream_writer": stream_writer}
        streaming_tools = self._create_langchain_tools(config=streaming_config)

        # Build a new graph with streaming tools
        streaming_llm_with_tools = self.llm.bind_tools(streaming_tools)

        # Build streaming graph that uses the streaming tools
        streaming_graph = self._build_streaming_graph(streaming_tools, streaming_llm_with_tools)
        self.logger.info("Built streaming graph with stream_writer-enabled tools")

        # Create initial message
        initial_message = HumanMessage(
            content=f"""Please analyze the following SMARTS alert for potential wash trading.

Alert file path: {alert_file_path}

Start by reading the alert, then systematically gather evidence using all available tools:
1. First, read the alert to understand the flagged trades
2. Check account relationships to find beneficial ownership
3. Query related accounts history for trading patterns
4. Analyze trade timing for pre-arrangement indicators
5. Perform counterparty analysis to detect circular patterns
6. Check market data for context

After collecting all evidence, provide your determination with detailed reasoning."""
        )

        try:
            # Use astream_events for real-time streaming
            self.logger.info("Starting astream_events iteration")

            # Track node transitions for emitting agent events
            last_node = None

            # Keep-alive tracking
            last_keepalive_time = time.time()
            KEEPALIVE_INTERVAL = 25  # seconds

            async for event in streaming_graph.astream_events(
                {"messages": [initial_message]},
                config={"recursion_limit": 50},
                version="v2",
            ):
                event_kind = event.get("event", "")
                event_name = event.get("name", "")
                event_data = event.get("data", {})

                self.logger.debug(f"LangGraph event: {event_kind} - {event_name}")

                # Yield any collected tool events first
                while collected_events:
                    tool_event = collected_events.pop(0)
                    yield tool_event

                # Map and emit relevant LangGraph events
                if event_kind == "on_chain_start":
                    if event_name in ("agent", "respond"):
                        if event_name != last_node:
                            last_node = event_name
                            if event_name == "agent":
                                yield event_mapper.create_agent_thinking_event(
                                    "Deciding next action..."
                                )
                            elif event_name == "respond":
                                yield event_mapper.create_agent_thinking_event(
                                    "Generating final determination..."
                                )

                elif event_kind == "on_tool_start":
                    # Map and yield tool start events
                    mapped_event = event_mapper.map_langgraph_event(event, event_kind)
                    if mapped_event:
                        self.logger.debug(f"Yielding tool_start event: {event_name}")
                        yield mapped_event

                elif event_kind == "on_tool_end":
                    # Map and yield tool end events
                    mapped_event = event_mapper.map_langgraph_event(event, event_kind)
                    if mapped_event:
                        self.logger.debug(f"Yielding tool_end event: {event_name}")
                        yield mapped_event

                # Emit keep-alive if needed (prevent connection timeouts during long operations)
                current_time = time.time()
                if current_time - last_keepalive_time >= KEEPALIVE_INTERVAL:
                    keepalive_event = event_mapper.create_keep_alive_event()
                    self.logger.debug("Emitting keep-alive event")
                    yield keepalive_event
                    last_keepalive_time = current_time

                elif event_kind == "on_chain_end":
                    if event_name == "respond":
                        # Extract final result
                        output = event_data.get("output", {})
                        messages = output.get("messages", [])
                        if messages:
                            last_msg = messages[-1]
                            if hasattr(last_msg, "content"):
                                content = last_msg.content
                                if isinstance(content, str) and content.startswith("{"):
                                    try:
                                        data = json.loads(content)
                                        decision = WashTradeDecision(**data)

                                        # Write outputs
                                        self._write_decision(decision)
                                        self._write_html_report(decision, alert_file_path)
                                        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                                        self._write_audit_log(decision, elapsed)

                                        # Emit completion event with full decision
                                        decision_dict = decision.model_dump(mode="json", exclude_none=True)
                                        yield event_mapper.create_analysis_complete_event(
                                            determination=decision.determination,
                                            confidence=decision.genuine_alert_confidence,
                                            summary=decision.key_findings[0] if decision.key_findings else "Analysis complete",
                                            decision=decision_dict,
                                        )

                                        self.logger.info(
                                            f"Streaming wash trade analysis completed in {elapsed:.2f}s: "
                                            f"{decision.determination}"
                                        )
                                        return

                                    except (json.JSONDecodeError, Exception) as e:
                                        self.logger.error(f"Failed to parse decision: {e}")

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(f"Streaming wash trade analysis failed after {elapsed:.2f}s: {e}", exc_info=True)
            yield event_mapper.create_error_event(
                str(e),
                stage="analysis",
                fatal=True,
            )
            raise

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
            "tools": [t.get_stats() for t in self.tool_instances]
        }
