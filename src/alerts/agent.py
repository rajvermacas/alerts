"""LangGraph agent for SMARTS Alert Analyzer.

This module implements the main agent that orchestrates tool calls
and produces the final determination for alert analysis.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from alerts.models import (
    AlertDecision,
    MarketContext,
    TraderBaselineAnalysis,
)
from alerts.reports.html_generator import HTMLReportGenerator
from alerts.prompts.system_prompt import (
    get_final_decision_prompt,
    get_system_prompt,
    load_few_shot_examples,
)
from alerts.tools import (
    AlertReaderTool,
    MarketDataTool,
    MarketNewsTool,
    PeerTradesTool,
    TraderHistoryTool,
    TraderProfileTool,
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


class AlertAnalyzerAgent:
    """LangGraph agent for analyzing SMARTS alerts.

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

        self.logger.info("Initializing AlertAnalyzerAgent")
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
            AlertReaderTool(self.llm, self.data_dir),
            TraderHistoryTool(self.llm, self.data_dir),
            TraderProfileTool(self.llm, self.data_dir),
            MarketNewsTool(self.llm, self.data_dir),
            MarketDataTool(self.llm, self.data_dir),
            PeerTradesTool(self.llm, self.data_dir),
        ]

    def _create_langchain_tools(self) -> list:
        """Convert tool instances to LangChain tools with proper schemas.

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

            # Create a wrapper function that captures the instance
            def make_tool_func(instance):
                def tool_func(**kwargs) -> str:
                    return instance(**kwargs)
                return tool_func

            # Create StructuredTool with explicit schema
            lc_tool = StructuredTool.from_function(
                func=make_tool_func(tool_instance),
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
        """
        self.logger.info("Respond node: generating structured decision")

        try:
            # Create LLM with structured output
            llm_structured = self.llm.with_structured_output(AlertDecision)

            # Build final decision prompt
            decision_prompt = get_final_decision_prompt()

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
            fallback = AlertDecision(
                alert_id="UNKNOWN",
                determination="NEEDS_HUMAN_REVIEW",
                genuine_alert_confidence=50,
                false_positive_confidence=50,
                key_findings=["Error occurred during analysis"],
                favorable_indicators=["Unable to determine"],
                risk_mitigating_factors=["Unable to determine"],
                trader_baseline_analysis=TraderBaselineAnalysis(
                    typical_volume="Unknown",
                    typical_sectors="Unknown",
                    typical_frequency="Unknown",
                    deviation_assessment="Analysis failed",
                ),
                market_context=MarketContext(
                    news_timeline="Unknown",
                    volatility_assessment="Unknown",
                    peer_activity_summary="Unknown",
                ),
                reasoning_narrative=f"Analysis failed with error: {str(e)}. Manual review required.",
                similar_precedent="Unable to determine due to error",
                recommended_action="REQUEST_MORE_DATA",
                data_gaps=["Complete re-analysis required"],
            )

            return {
                "messages": [AIMessage(content=fallback.model_dump_json(indent=2))]
            }

    def analyze(self, alert_file_path: Path) -> AlertDecision:
        """Analyze an alert and produce a determination.

        Args:
            alert_file_path: Path to the alert XML file

        Returns:
            AlertDecision with the determination and reasoning

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
                    decision = AlertDecision(**data)
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

    def _write_decision(self, decision: AlertDecision) -> Path:
        """Write decision to JSON file.

        Args:
            decision: AlertDecision to write

        Returns:
            Path to written file
        """
        output_file = self.output_dir / f"decision_{decision.alert_id}.json"

        self.logger.info(f"Writing decision to {output_file}")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(decision.model_dump_json(indent=2))

        return output_file

    def _write_html_report(self, decision: AlertDecision, alert_file_path: Path) -> Path:
        """Write decision to HTML report.

        Args:
            decision: AlertDecision to write
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

    def _write_audit_log(self, decision: AlertDecision, processing_time: float) -> None:
        """Append to audit log.

        Args:
            decision: AlertDecision to log
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
