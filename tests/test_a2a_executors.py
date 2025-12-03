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
from alerts.models import AlertDecision


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

        input_str = "'test data/alerts/alert.xml'"
        result = executor._extract_alert_path(input_str)
        assert result == "test data/alerts/alert.xml"

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

    def test_format_decision(self, tmp_path):
        """Test decision formatting."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        # Create sample decision
        decision = AlertDecision(
            alert_id="TEST-001",
            determination="ESCALATE",
            genuine_alert_confidence=85,
            false_positive_confidence=15,
            recommended_action="Escalate to senior investigator",
            similar_precedent="Example A",
            key_findings=["Finding 1", "Finding 2"],
            favorable_indicators=["Indicator 1", "Indicator 2"],
            risk_mitigating_factors=["Factor 1"],
            reasoning_narrative="This is the reasoning.",
            trader_baseline_analysis={},
            market_context={}
        )

        result = executor._format_decision(decision)

        assert "INSIDER TRADING ALERT ANALYSIS RESULT" in result
        assert "Alert ID: TEST-001" in result
        assert "Determination: ESCALATE" in result
        assert "Genuine Confidence: 85%" in result
        assert "Finding 1" in result
        assert "Finding 2" in result
        assert "Indicator 1" in result
        assert "Factor 1" in result
        assert "This is the reasoning." in result

    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path):
        """Test successful execution."""
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
        mock_decision = AlertDecision(
            alert_id="TEST-001",
            determination="ESCALATE",
            genuine_alert_confidence=85,
            false_positive_confidence=15,
            recommended_action="Escalate",
            similar_precedent="Example",
            key_findings=["Test"],
            favorable_indicators=["Test"],
            risk_mitigating_factors=["Test"],
            reasoning_narrative="Test",
            trader_baseline_analysis={},
            market_context={}
        )
        mock_agent.analyze.return_value = mock_decision
        executor._agent = mock_agent

        # Create context
        message = Mock()
        message.parts = [TextPart(kind="text", text=str(alert_file))]
        message.messageId = "msg-123"
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = str(alert_file)
        context.current_task = None

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
        context.current_task = None

        event_queue = AsyncMock(spec=EventQueue)

        # Execute (should handle error gracefully)
        await executor.execute(context, event_queue)

        # Should have sent error message
        assert event_queue.enqueue_event.called


class TestOrchestratorExecutor:
    """Test OrchestratorAgentExecutor functionality."""

    def test_init(self, tmp_path):
        """Test executor initialization."""
        data_dir = tmp_path / "data"
        insider_url = "http://localhost:10001"

        executor = OrchestratorAgentExecutor(data_dir, insider_url)

        assert executor.data_dir == data_dir
        assert executor.insider_trading_agent_url == insider_url
        assert executor._orchestrator is None

    def test_get_orchestrator(self, tmp_path):
        """Test lazy orchestrator creation."""
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

        # First call creates orchestrator
        orch1 = executor._get_orchestrator()
        assert orch1 is not None
        assert executor._orchestrator is orch1

        # Second call returns same instance
        orch2 = executor._get_orchestrator()
        assert orch2 is orch1

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
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")
        result = executor._extract_alert_path(input_str)
        assert result == expected

    def test_validate_request_valid(self, tmp_path):
        """Test validation with valid request."""
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

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
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

        # Missing message
        context = Mock(spec=RequestContext)
        context.message = None

        result = executor._validate_request(context)
        assert result is True  # True means invalid

    def test_format_response_success(self, tmp_path):
        """Test formatting successful routing response."""
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

        result_data = {
            "alert_id": "IT-001",
            "alert_type": "Insider Trading",
            "routed_to": "insider_trading_agent",
            "agent_response": {
                "status": "success",
                "response": {"determination": "ESCALATE"}
            }
        }

        formatted = executor._format_response(result_data)

        assert "ORCHESTRATOR ROUTING RESULT" in formatted
        assert "Alert ID: IT-001" in formatted
        assert "Alert Type: Insider Trading" in formatted
        assert "Routed to: insider_trading_agent" in formatted
        assert "success" in formatted

    def test_format_response_unsupported(self, tmp_path):
        """Test formatting unsupported alert type response."""
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

        result_data = {
            "alert_id": "MM-001",
            "alert_type": "Market Manipulation",
            "routed_to": None,
            "message": "Alert type not supported"
        }

        formatted = executor._format_response(result_data)

        assert "Market Manipulation" in formatted
        assert "not supported" in formatted or "No routing" in formatted

    def test_format_response_error(self, tmp_path):
        """Test formatting error response."""
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

        result_data = {
            "alert_id": "ERR-001",
            "alert_type": "Insider Trading",
            "routed_to": "insider_trading_agent",
            "agent_response": {
                "status": "error",
                "error": "Connection refused"
            }
        }

        formatted = executor._format_response(result_data)

        assert "error" in formatted.lower()
        assert "Connection refused" in formatted

    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path):
        """Test successful orchestrator execution."""
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

        executor = OrchestratorAgentExecutor(data_dir, "http://localhost:10001")

        # Mock orchestrator
        mock_orch = MagicMock()
        mock_orch.analyze_alert = AsyncMock(return_value={
            "alert_id": "IT-001",
            "routed_to": "insider_trading_agent",
            "agent_response": {"status": "success"}
        })
        executor._orchestrator = mock_orch

        # Create context
        message = Mock()
        message.parts = [TextPart(kind="text", text=str(alert_file))]
        message.messageId = "msg-123"
        context = Mock(spec=RequestContext)
        context.message = message
        context.get_user_input.return_value = str(alert_file)
        context.current_task = None

        event_queue = AsyncMock(spec=EventQueue)

        # Execute
        await executor.execute(context, event_queue)

        # Verify
        assert event_queue.enqueue_event.called
        mock_orch.analyze_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_invalid_request(self, tmp_path):
        """Test orchestrator execution with invalid request."""
        from a2a.utils.errors import ServerError

        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

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

    def test_format_decision_empty_lists(self, tmp_path):
        """Test decision formatting with empty lists."""
        mock_llm = MagicMock()
        executor = InsiderTradingAgentExecutor(mock_llm, tmp_path, tmp_path)

        decision = AlertDecision(
            alert_id="TEST-EMPTY",
            determination="NEEDS_HUMAN_REVIEW",
            genuine_alert_confidence=50,
            false_positive_confidence=50,
            recommended_action="Review manually",
            similar_precedent="None",
            key_findings=[],
            favorable_indicators=[],
            risk_mitigating_factors=[],
            reasoning_narrative="Insufficient data.",
            trader_baseline_analysis={},
            market_context={}
        )

        result = executor._format_decision(decision)
        assert "TEST-EMPTY" in result
        assert "NEEDS_HUMAN_REVIEW" in result

    def test_orchestrator_format_response_minimal(self, tmp_path):
        """Test formatting response with minimal data."""
        executor = OrchestratorAgentExecutor(tmp_path, "http://localhost:10001")

        result_data = {
            "alert_id": "MIN-001",
        }

        formatted = executor._format_response(result_data)
        assert "MIN-001" in formatted
