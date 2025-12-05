"""LangGraph agent for Insider Trading Alert Analysis.

This module implements the insider trading analyzer agent that orchestrates
tool calls and produces the final determination for insider trading alerts.

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

from alerts.models.insider_trading import (
    InsiderTradingDecision,
    MarketContext,
    TraderBaselineAnalysis,
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
    PeerTradesTool,
)

logger = logging.getLogger(__name__)


# Tool argument schemas
class ReadAlertArgs(BaseModel):
    """Arguments for the read_alert tool."""
    alert_file_path: str = Field(
        description="Path to the alert XML file to read (e.g., 'test_data/alerts/alert_genuine.xml')"
    )


class QueryTraderHistoryArgs(BaseModel):
    """Arguments for the query_trader_history tool."""
    trader_id: str = Field(description="Trader ID to query")
    symbol: str = Field(description="The flagged stock symbol")
    trade_date: str = Field(description="The flagged trade date in YYYY-MM-DD format")


class QueryTraderProfileArgs(BaseModel):
    """Arguments for the query_trader_profile tool."""
    trader_id: str = Field(description="Trader ID to query")


class QueryMarketNewsArgs(BaseModel):
    """Arguments for the query_market_news tool."""
    symbol: str = Field(description="Stock symbol to query")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: str = Field(description="End date in YYYY-MM-DD format")


class QueryMarketDataArgs(BaseModel):
    """Arguments for the query_market_data tool."""
    symbol: str = Field(description="Stock symbol to query")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: str = Field(description="End date in YYYY-MM-DD format")


class QueryPeerTradesArgs(BaseModel):
    """Arguments for the query_peer_trades tool."""
    symbol: str = Field(description="Stock symbol to query")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: str = Field(description="End date in YYYY-MM-DD format")


class InsiderTradingAnalyzerAgent:
    """LangGraph agent for analyzing SMARTS insider trading alerts.

    This agent uses a multi-tool approach to gather evidence and
    produce a structured determination for insider trading alerts.

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

        self.logger.info("Initializing InsiderTradingAnalyzerAgent")
        self.logger.info(f"Data directory: {data_dir}")
        self.logger.info(f"Output directory: {output_dir}")

        # Load few-shot examples
        examples_path = data_dir / "few_shot_examples.json"
        self.few_shot_examples = load_few_shot_examples(examples_path)
        if not self.few_shot_examples:
            raise FileNotFoundError(f"Few-shot examples not found: {examples_path}")

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
        return [
            # Common tools
            AlertReaderTool(self.llm, self.data_dir),
            TraderProfileTool(self.llm, self.data_dir),
            MarketDataTool(self.llm, self.data_dir),
            # Insider trading specific tools
            TraderHistoryTool(self.llm, self.data_dir),
            MarketNewsTool(self.llm, self.data_dir),
            PeerTradesTool(self.llm, self.data_dir),
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
            "query_trader_history": QueryTraderHistoryArgs,
            "query_trader_profile": QueryTraderProfileArgs,
            "query_market_news": QueryMarketNewsArgs,
            "query_market_data": QueryMarketDataArgs,
            "query_peer_trades": QueryPeerTradesArgs,
        }

        langchain_tools = []

        for tool_instance in self.tool_instances:
            # Get the schema for this tool
            args_schema = schema_map.get(tool_instance.name)
            if not args_schema:
                raise ValueError(f"No schema defined for tool: {tool_instance.name}")

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
            system_prompt = get_system_prompt(self.few_shot_examples)
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
        system_prompt = get_system_prompt(self.few_shot_examples)

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

        Raises:
            Exception: If structured decision generation fails (fail-fast)
        """
        self.logger.info("Respond node: generating structured decision")

        # Create LLM with structured output
        llm_structured = self.llm.with_structured_output(InsiderTradingDecision)

        # Build final decision prompt
        decision_prompt = get_final_decision_prompt()

        # Add decision prompt to conversation
        messages = state["messages"] + [
            HumanMessage(content=decision_prompt)
        ]

        # Get structured response
        decision = llm_structured.invoke(messages)

        # Fail-fast: If decision is None, log debug info and raise
        if decision is None:
            self._log_failed_response(state, messages, None, "LLM returned None decision")
            raise ValueError(
                "LLM returned None for structured decision. "
                "Check resources/debug/ for response details."
            )

        self.logger.info(
            f"Decision generated: {decision.determination} "
            f"(genuine: {decision.genuine_alert_confidence}%, "
            f"false_positive: {decision.false_positive_confidence}%)"
        )

        # Return as JSON message
        return {
            "messages": [AIMessage(content=decision.model_dump_json(indent=2))]
        }

    def _log_failed_response(
        self,
        state: MessagesState,
        messages: List[Any],
        raw_response: Any,
        error_reason: str,
    ) -> None:
        """Log failed LLM response to debug file for investigation.

        Args:
            state: Current graph state
            messages: Messages sent to LLM
            raw_response: Raw response from LLM (may be None)
            error_reason: Description of why the response failed
        """
        debug_dir = Path("resources/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        debug_file = debug_dir / f"insider_trading_failed_response_{timestamp}.json"

        debug_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error_reason": error_reason,
            "raw_response": str(raw_response) if raw_response else None,
            "messages_count": len(messages),
            "state_messages_count": len(state.get("messages", [])),
            "last_messages": [
                {
                    "type": type(msg).__name__,
                    "content": msg.content[:2000] if hasattr(msg, "content") else str(msg)[:2000],
                }
                for msg in messages[-5:]
            ],
        }

        debug_file.write_text(json.dumps(debug_data, indent=2, default=str))
        self.logger.error(
            f"Failed response logged to {debug_file.absolute()}. Reason: {error_reason}"
        )

    def analyze(self, alert_file_path: Path) -> InsiderTradingDecision:
        """Analyze an alert and produce a determination.

        Args:
            alert_file_path: Path to the alert XML file

        Returns:
            InsiderTradingDecision with the determination and reasoning

        Raises:
            FileNotFoundError: If alert file doesn't exist
            Exception: If analysis fails
        """
        start_time = datetime.now(timezone.utc)

        self.logger.info("=" * 60)
        self.logger.info(f"Starting analysis of alert: {alert_file_path}")
        self.logger.info("=" * 60)

        if not alert_file_path.exists():
            raise FileNotFoundError(f"Alert file not found: {alert_file_path}")

        # Store alert file path for HTML report generation
        self._current_alert_path = alert_file_path

        # Create initial message with alert file path
        initial_message = HumanMessage(
            content=f"""Please analyze the following SMARTS alert for potential insider trading.

Alert file path: {alert_file_path}

Start by reading the alert, then systematically gather evidence using all available tools.
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
                    decision = InsiderTradingDecision(**data)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse decision JSON: {e}")
                    raise
            else:
                self.logger.error("Last message is not valid JSON")
                raise ValueError("Agent did not produce valid structured output")

            # Calculate processing time
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.info(f"Analysis completed in {elapsed:.2f}s")

            # Write outputs
            self._write_decision(decision)
            self._write_html_report(decision, alert_file_path)
            self._write_audit_log(decision, elapsed)

            return decision

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(f"Analysis failed after {elapsed:.2f}s: {e}", exc_info=True)
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
        event_mapper = EventMapper(task_id=task_id, agent_name="insider_trading")
        collected_events: List[StreamEvent] = []

        self.logger.info("=" * 60)
        self.logger.info(f"Starting streaming analysis of alert: {alert_file_path}")
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
            content=f"""Please analyze the following SMARTS alert for potential insider trading.

Alert file path: {alert_file_path}

Start by reading the alert, then systematically gather evidence using all available tools.
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
                                        decision = InsiderTradingDecision(**data)

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
                                            f"Streaming analysis completed in {elapsed:.2f}s: "
                                            f"{decision.determination}"
                                        )
                                        return

                                    except (json.JSONDecodeError, Exception) as e:
                                        self.logger.error(f"Failed to parse decision: {e}")

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(f"Streaming analysis failed after {elapsed:.2f}s: {e}", exc_info=True)
            yield event_mapper.create_error_event(
                str(e),
                stage="analysis",
                fatal=True,
            )
            raise

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
            "tools": [t.get_stats() for t in self.tool_instances]
        }


# Backward compatibility alias
AlertAnalyzerAgent = InsiderTradingAnalyzerAgent
