"""Tests for analyze_request() context parameter flow.

Tests cover:
- AlertContext to context params conversion
- Context parameter passing to tools
- _build_context_params_from_alert() methods in agents

Architecture Note:
- AlertReaderTool.parse_alert_context() REMOVED
- Context now comes pre-parsed via request.alert_context
- Agents use _build_context_params_from_alert() instead
- See: .dev-resources/architecture/remove-alert-reader-tool.md
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from alerts.models.alert_context import (
    InsiderTradingAlertContext,
    WashTradeAlertContext,
    Trader,
    Trade,
    WashTradeFlaggedTrade,
)


class TestInsiderTradingContextParams:
    """Tests for InsiderTradingAnalyzerAgent._build_context_params_from_alert()."""

    @pytest.fixture
    def sample_it_context(self) -> InsiderTradingAlertContext:
        """Return sample InsiderTradingAlertContext."""
        return InsiderTradingAlertContext(
            alert_id="ITA-2024-001847",
            alert_type="Pre-Announcement Trading",
            rule_violated="MAR-03-001",
            generated_timestamp=datetime(2024, 3, 16, 10, 30, 0),
            trader=Trader(
                trader_id="T001",
                name="John Smith",
                department="Operations",
            ),
            trade=Trade(
                symbol="ACME",
                trade_date=date(2024, 3, 15),
                side="BUY",
                quantity=50000,
                price=Decimal("101.50"),
                total_value=Decimal("5075000"),
            ),
        )

    def test_builds_correct_context_params(
        self, sample_it_context, test_data_dir, mock_llm, output_dir
    ):
        """IT agent builds correct context params for each tool."""
        from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent

        agent = InsiderTradingAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        params = agent._build_context_params_from_alert(sample_it_context)

        # Verify market_news params
        assert params["query_market_news"]["symbol"] == "ACME"
        assert params["query_market_news"]["start_date"] == "2024-02-14"  # -30 days
        assert params["query_market_news"]["end_date"] == "2024-04-14"  # +30 days

        # Verify market_data params
        assert params["query_market_data"]["symbol"] == "ACME"
        assert params["query_market_data"]["start_date"] == "2024-02-14"
        assert params["query_market_data"]["end_date"] == "2024-04-14"

        # Verify trader_profile params
        assert params["query_trader_profile"]["trader_id"] == "T001"

        # Verify trader_history params
        assert params["query_trader_history"]["trader_id"] == "T001"
        assert params["query_trader_history"]["symbol"] == "ACME"
        assert params["query_trader_history"]["trade_date"] == "2024-03-15"

    def test_date_range_crosses_year_boundary(self, test_data_dir, mock_llm, output_dir):
        """Handles date range crossing year boundary."""
        from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent

        agent = InsiderTradingAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        context = InsiderTradingAlertContext(
            alert_id="ITA-2024-001",
            alert_type="Pre-Announcement Trading",
            rule_violated="MAR-03-001",
            generated_timestamp=datetime(2024, 1, 16, 10, 30, 0),
            trader=Trader(trader_id="T001", name="John Smith", department="Ops"),
            trade=Trade(
                symbol="ACME",
                trade_date=date(2024, 1, 15),
                side="BUY",
                quantity=1000,
                price=Decimal("100.00"),
                total_value=Decimal("100000"),
            ),
        )

        params = agent._build_context_params_from_alert(context)

        # Jan 15 - 30 days = Dec 16 (previous year)
        assert params["query_market_news"]["start_date"] == "2023-12-16"
        # Jan 15 + 30 days = Feb 14
        assert params["query_market_news"]["end_date"] == "2024-02-14"


class TestWashTradeContextParams:
    """Tests for WashTradeAnalyzerAgent._build_context_params_from_alert()."""

    @pytest.fixture
    def sample_wt_context(self) -> WashTradeAlertContext:
        """Return sample WashTradeAlertContext."""
        return WashTradeAlertContext(
            alert_id="WT-2024-001",
            alert_type="Self-Trade",
            rule_violated="SMARTS-WT-001",
            generated_timestamp=datetime(2024, 1, 16, 10, 30, 0),
            severity="HIGH",
            flagged_trades=[
                WashTradeFlaggedTrade(
                    sequence=1,
                    account_id="ACC-001",
                    account_name="Account Alpha",
                    trade_date=date(2024, 1, 15),
                    trade_time="14:32:15.123",
                    symbol="AAPL",
                    side="BUY",
                    quantity=10000,
                    price=Decimal("150.25"),
                    total_value=Decimal("1502500"),
                    counterparty_account="ACC-002",
                    order_id="ORD001",
                ),
                WashTradeFlaggedTrade(
                    sequence=2,
                    account_id="ACC-002",
                    account_name="Account Beta",
                    trade_date=date(2024, 1, 15),
                    trade_time="14:32:15.625",
                    symbol="AAPL",
                    side="SELL",
                    quantity=10000,
                    price=Decimal("150.25"),
                    total_value=Decimal("1502500"),
                    counterparty_account="ACC-001",
                    order_id="ORD002",
                ),
            ],
        )

    def test_builds_correct_context_params(
        self, sample_wt_context, test_data_dir, mock_llm, output_dir
    ):
        """WT agent builds correct context params for each tool."""
        from alerts.agents.wash_trade.agent import WashTradeAnalyzerAgent

        agent = WashTradeAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        params = agent._build_context_params_from_alert(sample_wt_context)

        # Verify market_data params
        assert params["query_market_data"]["symbol"] == "AAPL"
        assert params["query_market_data"]["start_date"] == "2023-12-16"  # -30 days
        assert params["query_market_data"]["end_date"] == "2024-01-22"  # +7 days

        # Verify account_relationships params (sorted account IDs)
        assert "ACC-001" in params["account_relationships"]["account_ids"]
        assert "ACC-002" in params["account_relationships"]["account_ids"]

        # Verify related_accounts_history params
        assert params["related_accounts_history"]["symbol"] == "AAPL"
        assert params["related_accounts_history"]["time_window"] == "30d"

        # Verify trade_timing params
        assert params["trade_timing"]["trade1_timestamp"] == "14:32:15.123"
        assert params["trade_timing"]["trade2_timestamp"] == "14:32:15.625"
        assert params["trade_timing"]["symbol"] == "AAPL"
        assert params["trade_timing"]["trade_quantity"] == "10000"

    def test_extracts_all_account_ids(self, test_data_dir, mock_llm, output_dir):
        """Extracts account IDs from all flagged trades."""
        from alerts.agents.wash_trade.agent import WashTradeAnalyzerAgent

        agent = WashTradeAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        # Create context with 3 unique accounts
        context = WashTradeAlertContext(
            alert_id="WT-2024-002",
            alert_type="Circular Trade",
            rule_violated="SMARTS-WT-002",
            generated_timestamp=datetime(2024, 3, 15, 10, 0, 0),
            severity="CRITICAL",
            flagged_trades=[
                WashTradeFlaggedTrade(
                    sequence=1,
                    account_id="ACC-A",
                    account_name="Alpha",
                    trade_date=date(2024, 3, 15),
                    trade_time="10:00:00.000",
                    symbol="XYZ",
                    side="BUY",
                    quantity=5000,
                    price=Decimal("50.00"),
                    total_value=Decimal("250000"),
                    counterparty_account="ACC-B",
                    order_id="O1",
                ),
                WashTradeFlaggedTrade(
                    sequence=2,
                    account_id="ACC-B",
                    account_name="Beta",
                    trade_date=date(2024, 3, 15),
                    trade_time="10:00:00.100",
                    symbol="XYZ",
                    side="SELL",
                    quantity=5000,
                    price=Decimal("50.00"),
                    total_value=Decimal("250000"),
                    counterparty_account="ACC-C",
                    order_id="O2",
                ),
                WashTradeFlaggedTrade(
                    sequence=3,
                    account_id="ACC-C",
                    account_name="Gamma",
                    trade_date=date(2024, 3, 15),
                    trade_time="10:00:00.200",
                    symbol="XYZ",
                    side="BUY",
                    quantity=5000,
                    price=Decimal("50.00"),
                    total_value=Decimal("250000"),
                    counterparty_account="ACC-A",
                    order_id="O3",
                ),
            ],
        )

        params = agent._build_context_params_from_alert(context)

        # All 3 accounts should be in the account_ids string
        account_ids = params["account_relationships"]["account_ids"]
        assert "ACC-A" in account_ids
        assert "ACC-B" in account_ids
        assert "ACC-C" in account_ids


class TestDateRangeCalculation:
    """Tests for date range calculation in context params."""

    def test_it_date_range_30_days_each_direction(
        self, test_data_dir, mock_llm, output_dir
    ):
        """IT uses +-30 days from trade date."""
        from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent

        agent = InsiderTradingAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        context = InsiderTradingAlertContext(
            alert_id="TEST",
            alert_type="Test",
            rule_violated="TEST",
            generated_timestamp=datetime(2024, 4, 1, 0, 0, 0),
            trader=Trader(trader_id="T1", name="Test", department="Test"),
            trade=Trade(
                symbol="TEST",
                trade_date=date(2024, 3, 31),  # March 31
                side="BUY",
                quantity=100,
                price=Decimal("1.00"),
                total_value=Decimal("100"),
            ),
        )

        params = agent._build_context_params_from_alert(context)

        # March 31 - 30 days = March 1
        assert params["query_market_news"]["start_date"] == "2024-03-01"
        # March 31 + 30 days = April 30
        assert params["query_market_news"]["end_date"] == "2024-04-30"

    def test_wt_date_range_30_before_7_after(self, test_data_dir, mock_llm, output_dir):
        """WT uses -30 days, +7 days from trade date."""
        from alerts.agents.wash_trade.agent import WashTradeAnalyzerAgent

        agent = WashTradeAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        context = WashTradeAlertContext(
            alert_id="WT-TEST",
            alert_type="Self-Trade",
            rule_violated="TEST",
            generated_timestamp=datetime(2024, 4, 1, 0, 0, 0),
            severity="HIGH",
            flagged_trades=[
                WashTradeFlaggedTrade(
                    sequence=1,
                    account_id="A1",
                    account_name="Test1",
                    trade_date=date(2024, 3, 25),  # March 25
                    trade_time="10:00:00",
                    symbol="TEST",
                    side="BUY",
                    quantity=100,
                    price=Decimal("1.00"),
                    total_value=Decimal("100"),
                    counterparty_account="A2",
                    order_id="O1",
                ),
                WashTradeFlaggedTrade(
                    sequence=2,
                    account_id="A2",
                    account_name="Test2",
                    trade_date=date(2024, 3, 25),
                    trade_time="10:00:01",
                    symbol="TEST",
                    side="SELL",
                    quantity=100,
                    price=Decimal("1.00"),
                    total_value=Decimal("100"),
                    counterparty_account="A1",
                    order_id="O2",
                ),
            ],
        )

        params = agent._build_context_params_from_alert(context)

        # March 25 - 30 days = Feb 24
        assert params["query_market_data"]["start_date"] == "2024-02-24"
        # March 25 + 7 days = April 1
        assert params["query_market_data"]["end_date"] == "2024-04-01"
