"""Pytest configuration and fixtures for SMARTS Alert Analyzer tests."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def test_data_dir() -> Path:
    """Return the path to test data directory."""
    return Path(__file__).parent.parent / "test_data"


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Return a temporary output directory."""
    output = tmp_path / "reports"
    output.mkdir(parents=True, exist_ok=True)
    return output


@pytest.fixture
def mock_llm() -> MagicMock:
    """Create a mock LLM for testing.

    Returns:
        MagicMock configured to behave like a LangChain LLM
    """
    mock = MagicMock()

    # Configure invoke to return a response with content
    mock_response = MagicMock()
    mock_response.content = "Mock LLM response for testing"
    mock.invoke.return_value = mock_response

    return mock


@pytest.fixture
def mock_llm_with_analysis() -> MagicMock:
    """Create a mock LLM that returns analysis-like responses.

    Returns:
        MagicMock with realistic analysis responses
    """
    mock = MagicMock()

    # Track call count to return different responses
    call_count = [0]

    def mock_invoke(prompt):
        call_count[0] += 1
        response = MagicMock()

        # Return different responses based on the prompt content
        prompt_str = str(prompt).lower()

        if "alert xml" in prompt_str or "parse" in prompt_str:
            response.content = """
Alert Summary:
- Alert ID: ITA-2024-001847
- Type: Pre-Announcement Trading
- Trader: John Smith (T001) from Operations
- Symbol: ACME, bought 50,000 shares at $101.50
- Anomaly Score: 87 (HIGH confidence)
- Temporal Proximity: 36 hours before M&A announcement
- Estimated Profit: $675,000
"""
        elif "baseline" in prompt_str or "history" in prompt_str:
            response.content = """
Trader Baseline Analysis:
- Typical Volume: 2,000 shares/day average
- Typical Sectors: Tech only (MSFT, AAPL, GOOGL, NVDA)
- Trading Frequency: Daily active trader
- Deviation: This trade is 25x normal volume in a completely new sector (Healthcare)
- Assessment: HIGHLY ANOMALOUS - first healthcare trade ever, massive volume
"""
        elif "profile" in prompt_str or "role" in prompt_str:
            response.content = """
Profile Assessment:
- Role: BACK_OFFICE (Operations)
- Access Level: LOW
- Trading Permitted: NO - Back-office employees should not be trading
- RED FLAGS: Back-office role with no legitimate information access is trading
- Risk Assessment: HIGH RISK - Role does not justify any trading activity
"""
        elif "news" in prompt_str:
            response.content = """
News Timeline Analysis:
- Pre-announcement: NO public news about ACME found before March 16
- Announcement: March 16, 9:00 AM - M&A announced at $150/share
- Public Information: None available that could justify the trade
- Assessment: Trade was made with NO public information to support it
"""
        elif "market data" in prompt_str or "price" in prompt_str:
            response.content = """
Market Analysis:
- Price Movement: Stock rose from $101.50 to $149.50 (47% gain)
- Volume: March 15 volume was 3x normal average
- Volatility: VIX elevated on announcement day
- Estimated Profit: ~$675,000 based on position size and price movement
"""
        elif "peer" in prompt_str:
            response.content = """
Peer Activity Analysis:
- Direction: Other traders were NET SELLING
- Isolation: The flagged trade was completely ISOLATED
- Comparison: No other internal traders bought ACME
- Assessment: Trade stands out as uniquely informed, against market flow
"""
        else:
            response.content = f"Mock analysis response #{call_count[0]}"

        return response

    mock.invoke.side_effect = mock_invoke

    return mock


@pytest.fixture
def sample_alert_xml() -> str:
    """Return sample alert XML content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
  <AlertID>TEST-001</AlertID>
  <AlertType>Pre-Announcement Trading</AlertType>
  <RuleViolated>MAR-03-001</RuleViolated>
  <GeneratedTimestamp>2024-03-16T10:30:00Z</GeneratedTimestamp>
  <Trader>
    <TraderID>T001</TraderID>
    <Name>Test Trader</Name>
    <Department>Operations</Department>
  </Trader>
  <SuspiciousActivity>
    <Symbol>TEST</Symbol>
    <TradeDate>2024-03-15</TradeDate>
    <Side>BUY</Side>
    <Quantity>10000</Quantity>
    <Price>100.00</Price>
    <TotalValue>1000000</TotalValue>
  </SuspiciousActivity>
  <AnomalyIndicators>
    <AnomalyScore>75</AnomalyScore>
    <ConfidenceLevel>HIGH</ConfidenceLevel>
    <TemporalProximity>24 hours before announcement</TemporalProximity>
    <EstimatedProfit>100000</EstimatedProfit>
  </AnomalyIndicators>
</SMARTSAlert>
"""


@pytest.fixture
def sample_trader_history_csv() -> str:
    """Return sample trader history CSV content."""
    return """trader_id,date,symbol,side,qty,price,sector
T001,2024-01-05,MSFT,BUY,2000,375.50,TECH
T001,2024-01-12,AAPL,SELL,1500,185.25,TECH
T001,2024-02-09,GOOGL,BUY,1800,188.50,TECH
"""


@pytest.fixture
def sample_trader_profiles_csv() -> str:
    """Return sample trader profiles CSV content."""
    return """trader_id,name,role,department,access_level,restrictions
T001,John Smith,BACK_OFFICE,Operations,LOW,No trading allowed
T002,Sarah Johnson,PORTFOLIO_MANAGER,Equities,HIGH,None
"""


@pytest.fixture
def sample_few_shot_examples() -> dict:
    """Return sample few-shot examples."""
    return {
        "examples": [
            {
                "id": "test_001",
                "scenario": "test_genuine",
                "alert_summary": "Test alert summary",
                "trader_baseline": "Test baseline",
                "market_context": "Test context",
                "peer_activity": "Test peer activity",
                "determination": "ESCALATE",
                "reasoning": "Test reasoning for escalation"
            },
            {
                "id": "test_002",
                "scenario": "test_false_positive",
                "alert_summary": "Test FP summary",
                "trader_baseline": "Test FP baseline",
                "market_context": "Test FP context",
                "peer_activity": "Test FP peer activity",
                "determination": "CLOSE",
                "reasoning": "Test reasoning for closing"
            }
        ]
    }


@pytest.fixture
def temp_test_data(tmp_path: Path, sample_alert_xml: str,
                   sample_trader_history_csv: str,
                   sample_trader_profiles_csv: str,
                   sample_few_shot_examples: dict) -> Path:
    """Create temporary test data directory with all required files.

    Returns:
        Path to temporary test data directory
    """
    # Create directories
    data_dir = tmp_path / "test_data"
    alerts_dir = data_dir / "alerts"
    alerts_dir.mkdir(parents=True)

    # Write alert file
    (alerts_dir / "test_alert.xml").write_text(sample_alert_xml)

    # Write CSV files
    (data_dir / "trader_history.csv").write_text(sample_trader_history_csv)
    (data_dir / "trader_profiles.csv").write_text(sample_trader_profiles_csv)

    # Write empty market data files
    (data_dir / "market_news.txt").write_text("===== TEST News Timeline =====\n2024-03-15 - No news")
    (data_dir / "market_data.csv").write_text("symbol,date,open,high,low,close,volume,vix\nTEST,2024-03-15,100,102,99,101,1000000,18")
    (data_dir / "peer_trades.csv").write_text("trader_id,date,symbol,side,qty,price,trader_type\nT101,2024-03-15,TEST,SELL,1000,100,INSTITUTIONAL")

    # Write few-shot examples
    (data_dir / "few_shot_examples.json").write_text(json.dumps(sample_few_shot_examples, indent=2))

    return data_dir


# Environment setup for tests
@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    # Only set if not already set (allows override in specific tests)
    if "OPENAI_API_KEY" not in os.environ:
        monkeypatch.setenv("OPENAI_API_KEY", "test-api-key-for-testing")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
