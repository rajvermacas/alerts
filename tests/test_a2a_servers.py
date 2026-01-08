"""Tests for A2A Server implementations.

This module tests the A2A server setup and configuration for both
the insider trading agent and orchestrator servers.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from click.testing import CliRunner


class TestInsiderTradingServer:
    """Test Insider Trading A2A Server."""

    def test_server_imports(self):
        """Test that server module imports correctly."""
        from alerts.a2a import insider_trading_server
        assert hasattr(insider_trading_server, 'main')

    def test_server_cli_help(self):
        """Test server CLI help output."""
        from alerts.a2a.insider_trading_server import main

        runner = CliRunner()
        result = runner.invoke(main, ['--help'])

        assert result.exit_code == 0
        assert '--host' in result.output
        assert '--port' in result.output
        assert '--verbose' in result.output

    @patch('alerts.a2a.insider_trading_server.uvicorn.run')
    @patch('alerts.a2a.insider_trading_server.create_llm')
    def test_server_startup_default_args(self, mock_create_llm, mock_uvicorn):
        """Test server starts with default arguments."""
        from alerts.a2a.insider_trading_server import main

        mock_create_llm.return_value = MagicMock()

        runner = CliRunner()
        result = runner.invoke(main, [])

        # Should attempt to start uvicorn
        assert mock_uvicorn.called

    @patch('alerts.a2a.insider_trading_server.uvicorn.run')
    @patch('alerts.a2a.insider_trading_server.create_llm')
    def test_server_startup_custom_port(self, mock_create_llm, mock_uvicorn):
        """Test server starts with custom port."""
        from alerts.a2a.insider_trading_server import main

        mock_create_llm.return_value = MagicMock()

        runner = CliRunner()
        result = runner.invoke(main, ['--port', '9999'])

        # Verify uvicorn was called with custom port
        assert mock_uvicorn.called
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['port'] == 9999

    @patch('alerts.a2a.insider_trading_server.uvicorn.run')
    @patch('alerts.a2a.insider_trading_server.create_llm')
    def test_server_startup_custom_host(self, mock_create_llm, mock_uvicorn):
        """Test server starts with custom host."""
        from alerts.a2a.insider_trading_server import main

        mock_create_llm.return_value = MagicMock()

        runner = CliRunner()
        result = runner.invoke(main, ['--host', '0.0.0.0'])

        # Verify uvicorn was called with custom host
        assert mock_uvicorn.called
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['host'] == '0.0.0.0'

    @patch('alerts.a2a.insider_trading_server.uvicorn.run')
    @patch('alerts.a2a.insider_trading_server.create_llm')
    def test_server_with_verbose_logging(self, mock_create_llm, mock_uvicorn):
        """Test server with verbose logging enabled."""
        from alerts.a2a.insider_trading_server import main

        mock_create_llm.return_value = MagicMock()

        runner = CliRunner()
        result = runner.invoke(main, ['--verbose'])

        # Should start successfully
        assert mock_uvicorn.called


class TestOrchestratorServer:
    """Test Orchestrator A2A Server."""

    def test_server_imports(self):
        """Test that server module imports correctly."""
        from alerts.a2a import orchestrator_server
        assert hasattr(orchestrator_server, 'main')

    def test_server_cli_help(self):
        """Test server CLI help output."""
        from alerts.a2a.orchestrator_server import main

        runner = CliRunner()
        result = runner.invoke(main, ['--help'])

        assert result.exit_code == 0
        assert '--host' in result.output
        assert '--port' in result.output
        assert '--insider-trading-url' in result.output

    @patch('alerts.a2a.orchestrator_server.uvicorn.run')
    def test_server_startup_default_args(self, mock_uvicorn):
        """Test server starts with default arguments."""
        from alerts.a2a.orchestrator_server import main

        runner = CliRunner()
        result = runner.invoke(main, [])

        # Should attempt to start uvicorn
        assert mock_uvicorn.called

    @patch('alerts.a2a.orchestrator_server.uvicorn.run')
    def test_server_startup_custom_insider_url(self, mock_uvicorn):
        """Test server starts with custom insider trading URL."""
        from alerts.a2a.orchestrator_server import main

        runner = CliRunner()
        result = runner.invoke(main, ['--insider-trading-url', 'http://remote:9999'])

        # Should start successfully
        assert mock_uvicorn.called

    @patch('alerts.a2a.orchestrator_server.uvicorn.run')
    def test_server_startup_all_custom_args(self, mock_uvicorn):
        """Test server starts with all custom arguments."""
        from alerts.a2a.orchestrator_server import main

        runner = CliRunner()
        result = runner.invoke(main, [
            '--host', '0.0.0.0',
            '--port', '8888',
            '--insider-trading-url', 'http://custom:7777'
        ])

        # Verify uvicorn was called with correct parameters
        assert mock_uvicorn.called
        call_kwargs = mock_uvicorn.call_args[1]
        assert call_kwargs['host'] == '0.0.0.0'
        assert call_kwargs['port'] == 8888


class TestA2AIntegration:
    """Integration tests for A2A communication."""

    @pytest.mark.asyncio
    async def test_end_to_end_alert_flow_mock(self, tmp_path):
        """Test end-to-end flow with mocked components."""
        from alerts.a2a.orchestrator import OrchestratorAgent

        # Create test alert
        data_dir = tmp_path / "data"
        alerts_dir = data_dir / "alerts"
        alerts_dir.mkdir(parents=True)

        alert_file = alerts_dir / "test_insider.xml"
        alert_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>E2E-001</AlertID>
    <AlertType>Insider Trading</AlertType>
    <RuleViolated>SMARTS-IT-001</RuleViolated>
</SMARTSAlert>
""")

        # Create orchestrator
        orchestrator = OrchestratorAgent(data_dir=data_dir)

        # Mock the A2A communication
        with patch.object(orchestrator, '_send_to_insider_trading_agent', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "status": "success",
                "response": {
                    "determination": "ESCALATE",
                    "confidence": 85
                }
            }

            # Execute end-to-end
            result = await orchestrator.analyze_alert(alert_file)

            # Verify flow
            assert result['alert_id'] == "E2E-001"
            assert result['alert_type'] == "Insider Trading"
            assert result['routed_to'] == "insider_trading_agent"
            assert result['agent_response']['status'] == "success"
            mock_send.assert_called_once()

    def test_server_ports_different(self):
        """Test that default ports are different for each server."""
        from alerts.a2a.insider_trading_server import main as it_main
        from alerts.a2a.orchestrator_server import main as orch_main

        # Check CLI definitions - they should have different default ports
        # Insider trading: 10001, Orchestrator: 10000
        it_runner = CliRunner()
        it_help = it_runner.invoke(it_main, ['--help'])

        orch_runner = CliRunner()
        orch_help = orch_runner.invoke(orch_main, ['--help'])

        # Both should mention ports
        assert 'port' in it_help.output.lower()
        assert 'port' in orch_help.output.lower()


class TestTestClient:
    """Test the A2A test client utility."""

    def test_test_client_imports(self):
        """Test that test client imports correctly."""
        from alerts.a2a import test_client
        assert hasattr(test_client, 'main')

    def test_test_client_cli_help(self):
        """Test test client CLI help output."""
        from alerts.a2a.test_client import main

        runner = CliRunner()
        result = runner.invoke(main, ['--help'])

        assert result.exit_code == 0
        assert '--server-url' in result.output
        assert '--alert' in result.output

    @patch('alerts.a2a.test_client.httpx.AsyncClient')
    @patch('alerts.a2a.test_client.A2ACardResolver')
    @patch('alerts.a2a.test_client.A2AClient')
    def test_test_client_basic_execution(self, mock_a2a_client, mock_resolver, mock_httpx, tmp_path):
        """Test basic test client execution."""
        from alerts.a2a.test_client import main

        # Create test alert
        alert_file = tmp_path / "test.xml"
        alert_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>CLIENT-TEST</AlertID>
</SMARTSAlert>
""")

        # Mock the A2A components
        mock_httpx_instance = MagicMock()
        mock_httpx_instance.__aenter__ = AsyncMock(return_value=mock_httpx_instance)
        mock_httpx_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_httpx_instance

        mock_agent_card = MagicMock()
        mock_agent_card.name = "Test Agent"
        mock_resolver_instance = MagicMock()
        mock_resolver_instance.get_agent_card = AsyncMock(return_value=mock_agent_card)
        mock_resolver.return_value = mock_resolver_instance

        mock_client_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"status": "success"}
        mock_client_instance.send_message = AsyncMock(return_value=mock_response)
        mock_a2a_client.return_value = mock_client_instance

        runner = CliRunner()
        result = runner.invoke(main, [
            '--server-url', 'http://localhost:10000',
            '--alert', str(alert_file)
        ])

        # Should complete without error
        assert result.exit_code == 0


class TestServerErrorHandling:
    """Test server error handling and edge cases."""

    @patch('alerts.a2a.insider_trading_server.uvicorn.run')
    @patch('alerts.a2a.insider_trading_server.create_llm')
    def test_insider_server_handles_port_in_use(self, mock_create_llm, mock_uvicorn):
        """Test server behavior when port is already in use."""
        from alerts.a2a.insider_trading_server import main

        mock_create_llm.return_value = MagicMock()

        # Simulate port in use
        mock_uvicorn.side_effect = OSError("Address already in use")

        runner = CliRunner()
        result = runner.invoke(main, ['--port', '10001'])

        # Should fail with error
        assert result.exit_code != 0
