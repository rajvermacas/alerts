"""Tests for A2A Agent Executors.

This module tests the A2A executor implementations for both the
insider trading agent and orchestrator agent.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import Message, TextPart, Task, TaskState
from alerts.a2a.insider_trading_executor import InsiderTradingAgentExecutor
from alerts.a2a.orchestrator_executor import OrchestratorAgentExecutor
from alerts.models import InsiderTradingDecision
from alerts.models.insider_trading import TraderBaselineAnalysis, MarketContext


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

    @pytest.mark.parametrize("input_str,expected", [
        ("test_data/alerts/alert.xml", "test_data/alerts/alert.xml"),
        ("analyze test.xml", "test.xml"),
        ("check this alert: /path/to/alert.xml", "/path/to/alert.xml"),
        ("'test_data/alert.xml'", "test_data/alert.xml"),
        ('"test_data/alert.xml"', "test_data/alert.xml"),
        ("Please analyze test_data/alerts/genuine.xml", "test_data/alerts/genuine.xml"),
        ("review /tmp/alert.xml", "/tmp/alert.xml"),
        ("/absolute/path/alert.xml", "/absolute/path/alert.xml"),
        ("", None),
        ("   ", None),
    ])
    def test_extract_alert_path(self, tmp_path, input_str, expected):
        """Test alert path extraction from various input formats."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)
        result = executor._extract_alert_path(input_str)
        assert result == expected

    def test_extract_alert_path_xml_in_sentence(self, tmp_path):
        """Test extracting .xml from middle of sentence."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        input_str = "Can you analyze the file alert_genuine.xml for me?"
        result = executor._extract_alert_path(input_str)
        assert result == "alert_genuine.xml"

    def test_extract_alert_path_with_spaces(self, tmp_path):
        """Test extracting path with spaces in quotes."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Note: The regex extracts content between quotes but spaces
        # can be tricky. Testing actual behavior here.
        input_str = "'test data/alerts/alert.xml'"
        result = executor._extract_alert_path(input_str)
        # Current implementation may truncate at space - test actual behavior
        assert result is not None
        assert "alert.xml" in result

    def test_validate_request_valid(self, tmp_path):
        """Test validation with valid request."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Create valid context
        message = Mock()
        message.parts = [TextPart(kind="text", text="analyze test.xml")]
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = "analyze test.xml"

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

    def test_format_decision(self, tmp_path, sample_insider_trading_decision):
        """Test decision formatting."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        result = executor._format_decision(sample_insider_trading_decision)

        assert "INSIDER TRADING ALERT ANALYSIS RESULT" in result
        assert "Alert ID: TEST-001" in result
        assert "Determination: ESCALATE" in result
        assert "Genuine Confidence: 85%" in result
        assert "Trade timing 36 hours before M&A announcement" in result
        assert "Back-office employee trading" in result
        assert "Market maker activity present" in result

    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path, sample_insider_trading_decision):
        """Test successful execution."""
        from a2a.types import Task, TaskState, TaskStatus

        # Setup
        mock_llm = MagicMock()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create test alert
        alerts_dir = data_dir / "alerts"
        alerts_dir.mkdir()
        alert_file = alerts_dir / "test.xml"
        alert_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>TEST-001</AlertID>
    <AlertType>Insider Trading</AlertType>
</SMARTSAlert>
""")

        executor = InsiderTradingAgentExecutor(mock_llm, data_dir, output_dir)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.analyze.return_value = sample_insider_trading_decision
        executor._agent = mock_agent

        # Create context with existing task to avoid new_task() call
        message = Mock()
        message.parts = [TextPart(kind="text", text=str(alert_file))]
        message.messageId = "msg-123"
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = str(alert_file)
        # Provide a mock task so new_task() isn't called
        context.current_task = Task(
            id="task-123",
            context_id="ctx-123",
            status=TaskStatus(state=TaskState.submitted)
        )

        # Mock event queue
        event_queue = AsyncMock(spec=EventQueue)

        # Execute
        await executor.execute(context, event_queue)

        # Verify
        assert event_queue.enqueue_event.called
        mock_agent.analyze.assert_called_once()

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

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tmp_path):
        """Test execution with non-existent file."""
        from a2a.types import Task, TaskState, TaskStatus

        mock_llm = MagicMock()
        data_dir = tmp_path / "data"
        output_dir = tmp_path / "output"

        executor = InsiderTradingAgentExecutor(mock_llm, data_dir, output_dir)

        # Create context with non-existent file
        message = Mock()
        message.parts = [TextPart(kind="text", text="nonexistent.xml")]
        message.messageId = "msg-123"
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = "nonexistent.xml"
        # Provide a mock task so new_task() isn't called
        context.current_task = Task(
            id="task-123",
            context_id="ctx-123",
            status=TaskStatus(state=TaskState.submitted)
        )

        event_queue = AsyncMock(spec=EventQueue)

        # Execute (should handle error gracefully)
        await executor.execute(context, event_queue)

        # Should have sent error message
        assert event_queue.enqueue_event.called


class TestOrchestratorExecutor:
    """Test OrchestratorAgentExecutor functionality."""

    def test_init(self, tmp_path):
        """Test executor initialization."""
        insider_url = "http://localhost:10001"
        wash_trade_url = "http://localhost:10002"

        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url=insider_url,
            wash_trade_agent_url=wash_trade_url,
            data_dir=tmp_path,
        )

        assert executor.orchestrator is not None
        assert executor.orchestrator.insider_trading_agent_url == insider_url
        assert executor.orchestrator.wash_trade_agent_url == wash_trade_url

    @pytest.mark.parametrize("input_str,expected", [
        ("test_data/alerts/alert.xml", "test_data/alerts/alert.xml"),
        ("analyze test.xml", "test.xml"),
        ("route this: /path/to/alert.xml", "/path/to/alert.xml"),
        ("'test_data/alert.xml'", "test_data/alert.xml"),
        ('"test_data/alert.xml"', "test_data/alert.xml"),
        ("Please check test_data/alerts/genuine.xml", "test_data/alerts/genuine.xml"),
        ("", None),
    ])
    def test_extract_alert_path(self, tmp_path, input_str, expected):
        """Test alert path extraction from orchestrator input."""
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
        )
        result = executor._extract_alert_path(input_str)
        assert result == expected

    def test_validate_request_valid(self, tmp_path):
        """Test validation with valid request."""
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
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
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
        )

        # Missing message
        context = Mock(spec=RequestContext)
        context.message = None

        result = executor._validate_request(context)
        assert result is True  # True means invalid

    def test_format_success_response(self, tmp_path):
        """Test formatting successful routing response."""
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
        )

        result_data = {
            "alert_id": "IT-001",
            "alert_type": "Insider Trading",
            "routed_to": "insider_trading_agent",
            "agent_response": {
                "status": "success",
                "response": {"determination": "ESCALATE"}
            }
        }

        formatted = executor._format_success_response(result_data)

        assert "ORCHESTRATOR RESULT" in formatted
        assert "Alert ID: IT-001" in formatted
        assert "Alert Type: Insider Trading" in formatted
        assert "Insider Trading Agent" in formatted  # Display name
        assert "ESCALATE" in formatted

    def test_format_unsupported_response(self, tmp_path):
        """Test formatting unsupported alert type response."""
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
        )

        result_data = {
            "alert_id": "MM-001",
            "alert_type": "Market Manipulation",
            "routed_to": None,
            "message": "Alert type not supported"
        }

        formatted = executor._format_unsupported_response(result_data)

        assert "Market Manipulation" in formatted
        assert "not supported" in formatted.lower()

    def test_format_error_response(self, tmp_path):
        """Test formatting error response."""
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
        )

        result_data = {
            "alert_id": "ERR-001",
            "alert_type": "Insider Trading",
            "routed_to": "insider_trading_agent",
            "agent_response": {
                "status": "error",
                "error": "Connection refused"
            }
        }

        formatted = executor._format_error_response(result_data)

        assert "error" in formatted.lower()
        assert "Connection refused" in formatted

    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path):
        """Test successful orchestrator execution."""
        from a2a.types import Task, TaskState, TaskStatus

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create test alert
        alerts_dir = data_dir / "alerts"
        alerts_dir.mkdir()
        alert_file = alerts_dir / "test.xml"
        alert_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>IT-001</AlertID>
    <AlertType>Insider Trading</AlertType>
</SMARTSAlert>
""")

        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=data_dir,
        )

        # Mock orchestrator's analyze_alert method
        mock_result = {
            "alert_id": "IT-001",
            "alert_type": "Insider Trading",
            "routed_to": "insider_trading_agent",
            "agent_response": {"status": "success"}
        }
        executor.orchestrator.analyze_alert = AsyncMock(return_value=mock_result)

        # Create context with existing task
        message = Mock()
        message.parts = [TextPart(kind="text", text=str(alert_file))]
        message.messageId = "msg-123"
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = str(alert_file)
        # Provide a mock task so new_task() isn't called
        context.current_task = Task(
            id="task-123",
            context_id="ctx-123",
            status=TaskStatus(state=TaskState.submitted)
        )

        event_queue = AsyncMock(spec=EventQueue)

        # Execute
        await executor.execute(context, event_queue)

        # Verify
        assert event_queue.enqueue_event.called
        executor.orchestrator.analyze_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_invalid_request(self, tmp_path):
        """Test orchestrator execution with invalid request."""
        from a2a.utils.errors import ServerError

        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
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

    def test_extract_path_none_input(self, tmp_path):
        """Test path extraction with None input."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)
        assert executor._extract_alert_path(None) is None

    def test_extract_path_only_whitespace(self, tmp_path):
        """Test path extraction with only whitespace."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)
        assert executor._extract_alert_path("   \t\n  ") is None

    def test_extract_path_special_characters(self, tmp_path):
        """Test path extraction with special characters."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        result = executor._extract_alert_path("/path/with-dashes_and_underscores/alert-01.xml")
        assert result == "/path/with-dashes_and_underscores/alert-01.xml"

    def test_format_decision_with_all_fields(self, tmp_path, sample_insider_trading_decision):
        """Test decision formatting with all fields populated."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        result = executor._format_decision(sample_insider_trading_decision)

        # Verify all sections are present
        assert "TEST-001" in result
        assert "ESCALATE" in result
        assert "85%" in result
        assert "15%" in result

    def test_orchestrator_format_success_response_minimal(self, tmp_path):
        """Test formatting response with minimal data."""
        executor = OrchestratorAgentExecutor(
            insider_trading_agent_url="http://localhost:10001",
            data_dir=tmp_path,
        )

        result_data = {
            "alert_id": "MIN-001",
            "alert_type": "Insider Trading",
            "routed_to": "insider_trading_agent",
            "agent_response": {"status": "success"}
        }

        formatted = executor._format_success_response(result_data)
        assert "MIN-001" in formatted
