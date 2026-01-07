"""Tests for A2A Agent Executors.

This module tests the A2A executor implementations for Proactive Info Flow mode.
Executors now only accept AnalysisRequest payloads prefixed with
PROACTIVE_INFO_FLOW_REQUEST:
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import Message, TextPart, Task, TaskState

from alerts.a2a.insider_trading_executor import (
    InsiderTradingAgentExecutor,
    PROACTIVE_INFO_FLOW_PREFIX,
)
from alerts.a2a.orchestrator_executor import OrchestratorAgentExecutor
from alerts.models.insider_trading import InsiderTradingDecision
from alerts.models.request import AnalysisRequest, ToolInput


class TestInsiderTradingExecutor:
    """Test InsiderTradingAgentExecutor functionality."""

    def test_init(self, tmp_path):
        """Test executor initialization."""
        mock_llm = MagicMock()
        data_dir = tmp_path / "data"
        output_dir = tmp_path / "output"

        executor = InsiderTradingAgentExecutor(mock_llm, data_dir, output_dir)

        assert executor.llm == mock_llm
        assert executor.data_dir == data_dir
        assert executor.output_dir == output_dir
        assert executor._agent is None

    def test_get_agent(self, temp_test_data, tmp_path):
        """Test lazy agent creation."""
        mock_llm = MagicMock()
        # Use temp_test_data which includes few_shot_examples.json
        data_dir = temp_test_data
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        executor = InsiderTradingAgentExecutor(mock_llm, data_dir, output_dir)

        # First call creates agent
        agent1 = executor._get_agent()
        assert agent1 is not None
        assert executor._agent is agent1

        # Second call returns same instance
        agent2 = executor._get_agent()
        assert agent2 is agent1

    def test_validate_request_valid(self, tmp_path):
        """Test validation with valid request."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Create valid context
        message = Mock()
        message.parts = [TextPart(kind="text", text="PROACTIVE_INFO_FLOW_REQUEST:{}")]
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = "PROACTIVE_INFO_FLOW_REQUEST:{}"

        result = executor._validate_request(context)
        assert result is False  # False means valid

    def test_validate_request_no_message(self, tmp_path):
        """Test validation with missing message."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        context = Mock(spec=RequestContext)
        context.message = None

        result = executor._validate_request(context)
        assert result is True  # True means invalid

    def test_validate_request_no_parts(self, tmp_path):
        """Test validation with missing parts."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        message = Mock()
        message.parts = []
        context = Mock(spec=RequestContext)
        context.message = message

        result = executor._validate_request(context)
        assert result is True  # True means invalid

    def test_validate_request_empty_text(self, tmp_path):
        """Test validation with empty user input."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        message = Mock()
        message.parts = [TextPart(kind="text", text="   ")]
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = "   "

        result = executor._validate_request(context)
        assert result is True  # True means invalid

    def test_is_proactive_info_flow_request(self, tmp_path):
        """Test Proactive Info Flow request detection."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Valid proactive info flow request
        valid_input = f"{PROACTIVE_INFO_FLOW_PREFIX}{{\"agent_type\": \"insider_trading\"}}"
        assert executor._is_proactive_info_flow_request(valid_input) is True

        # Invalid - no prefix
        assert executor._is_proactive_info_flow_request("test.xml") is False
        assert executor._is_proactive_info_flow_request("analyze alert") is False

    def test_parse_analysis_request_valid(self, tmp_path):
        """Test parsing valid AnalysisRequest."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Create valid request JSON with all required tools for insider_trading
        request = AnalysisRequest(
            alert_xml="<Alert/>",
            agent_type="insider_trading",
            tool_data={
                "alert_reader": ToolInput(format="xml", data="<Alert/>"),
                "market_news": ToolInput(format="txt", data="Some news"),
                "market_data": ToolInput(format="csv", data="date,price\n2024-01-01,100"),
                "trader_profile": ToolInput(format="csv", data="id,name\n1,John"),
                "trader_history": ToolInput(format="csv", data="date,amount\n2024-01-01,1000"),
            }
        )
        input_str = f"{PROACTIVE_INFO_FLOW_PREFIX}{request.model_dump_json()}"

        parsed = executor._parse_analysis_request(input_str)

        assert parsed.agent_type == "insider_trading"
        assert parsed.alert_xml == "<Alert/>"
        assert "alert_reader" in parsed.tool_data
        assert "market_news" in parsed.tool_data
        assert "trader_profile" in parsed.tool_data

    def test_parse_analysis_request_invalid_json(self, tmp_path):
        """Test parsing invalid JSON."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        input_str = f"{PROACTIVE_INFO_FLOW_PREFIX}{{invalid json}}"

        with pytest.raises(ValueError) as exc_info:
            executor._parse_analysis_request(input_str)

        assert "Failed to parse AnalysisRequest" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_invalid_request(self, tmp_path):
        """Test execution with invalid request."""
        from a2a.utils.errors import ServerError

        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Create invalid context (no message)
        context = Mock(spec=RequestContext)
        context.message = None

        event_queue = AsyncMock(spec=EventQueue)

        # Execute and expect error
        with pytest.raises(ServerError):
            await executor.execute(context, event_queue)


class TestOrchestratorExecutor:
    """Test OrchestratorAgentExecutor functionality."""

    def test_init(self, tmp_path):
        """Test executor initialization."""
        insider_url = "http://localhost:10001"
        wash_trade_url = "http://localhost:10002"

        executor = OrchestratorAgentExecutor(insider_url, wash_trade_url)

        # URLs are stored in the orchestrator object
        assert executor.orchestrator is not None
        assert executor.orchestrator.insider_trading_agent_url == insider_url
        assert executor.orchestrator.wash_trade_agent_url == wash_trade_url

    def test_extract_alert_path(self, tmp_path):
        """Test alert path extraction from orchestrator input."""
        executor = OrchestratorAgentExecutor(
            "http://localhost:10001",
            "http://localhost:10002"
        )
        # Test various input formats
        assert executor._extract_alert_path("test_data/alerts/alert.xml") == "test_data/alerts/alert.xml"
        assert executor._extract_alert_path("analyze test.xml") == "test.xml"
        assert executor._extract_alert_path("'test_data/alert.xml'") == "test_data/alert.xml"
        assert executor._extract_alert_path("") is None

    def test_validate_request_valid(self, tmp_path):
        """Test validation with valid request."""
        executor = OrchestratorAgentExecutor(
            "http://localhost:10001",
            "http://localhost:10002"
        )

        # Create valid context
        message = Mock()
        message.parts = [TextPart(kind="text", text="route test.xml")]
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = "route test.xml"

        result = executor._validate_request(context)
        assert result is False  # False means valid

    def test_validate_request_invalid(self, tmp_path):
        """Test validation with invalid request."""
        executor = OrchestratorAgentExecutor(
            "http://localhost:10001",
            "http://localhost:10002"
        )

        # Missing message
        context = Mock(spec=RequestContext)
        context.message = None

        result = executor._validate_request(context)
        assert result is True  # True means invalid

    @pytest.mark.asyncio
    async def test_execute_invalid_request(self, tmp_path):
        """Test orchestrator execution with invalid request."""
        from a2a.utils.errors import ServerError

        executor = OrchestratorAgentExecutor(
            "http://localhost:10001",
            "http://localhost:10002"
        )

        # Invalid context
        context = Mock(spec=RequestContext)
        context.message = None

        event_queue = AsyncMock(spec=EventQueue)

        # Execute and expect error
        with pytest.raises(ServerError):
            await executor.execute(context, event_queue)


class TestExecutorEdgeCases:
    """Test edge cases and error handling."""

    def test_proactive_info_flow_prefix(self, tmp_path):
        """Test that the PROACTIVE_INFO_FLOW_PREFIX constant is defined."""
        from alerts.a2a.insider_trading_executor import PROACTIVE_INFO_FLOW_PREFIX

        assert PROACTIVE_INFO_FLOW_PREFIX == "PROACTIVE_INFO_FLOW_REQUEST:"

    def test_executor_rejects_legacy_mode(self, tmp_path):
        """Test that executors reject non-Proactive Info Flow requests."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Legacy file path mode should be rejected
        assert executor._is_proactive_info_flow_request("test.xml") is False
        assert executor._is_proactive_info_flow_request("/path/to/alert.xml") is False
        assert executor._is_proactive_info_flow_request("analyze alert.xml") is False
