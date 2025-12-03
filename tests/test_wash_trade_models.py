"""Tests for Wash Trade Decision models.

This module tests the Pydantic models used for wash trade analysis.
"""

import pytest
from pydantic import ValidationError

from alerts.models.wash_trade import (
    RelationshipNode,
    RelationshipEdge,
    RelationshipNetwork,
    TimingPattern,
    TradeFlow,
    CounterpartyPattern,
    HistoricalPatternSummary,
    WashTradeDecision,
    WashTradeFewShotExample,
    WashTradeFewShotCollection,
)


class TestRelationshipNode:
    """Tests for RelationshipNode model."""

    def test_valid_node(self):
        """Test creating a valid relationship node."""
        node = RelationshipNode(
            account_id="ACC-001",
            beneficial_owner_id="BO-123",
            beneficial_owner_name="John Smith",
            relationship_type="direct",
            is_flagged=True,
        )
        assert node.account_id == "ACC-001"
        assert node.beneficial_owner_id == "BO-123"
        assert node.beneficial_owner_name == "John Smith"
        assert node.relationship_type == "direct"
        assert node.is_flagged is True

    def test_node_default_is_flagged(self):
        """Test node with default is_flagged value."""
        node = RelationshipNode(
            account_id="ACC-002",
            beneficial_owner_id="BO-456",
            beneficial_owner_name="Jane Doe",
            relationship_type="corporate",
        )
        assert node.is_flagged is False

    def test_valid_relationship_types(self):
        """Test all valid relationship types."""
        valid_types = [
            "direct", "family_trust", "corporate", "nominee",
            "market_maker", "hedge_book", "spousal", "intermediary"
        ]
        for rtype in valid_types:
            node = RelationshipNode(
                account_id="ACC-001",
                beneficial_owner_id="BO-001",
                beneficial_owner_name="Test",
                relationship_type=rtype,
            )
            assert node.relationship_type == rtype


class TestRelationshipEdge:
    """Tests for RelationshipEdge model."""

    def test_valid_edge(self):
        """Test creating a valid relationship edge."""
        edge = RelationshipEdge(
            from_account="ACC-001",
            to_account="ACC-002",
            edge_type="trade",
            trade_details="10K AAPL @ $150",
            is_suspicious=True,
        )
        assert edge.from_account == "ACC-001"
        assert edge.to_account == "ACC-002"
        assert edge.edge_type == "trade"
        assert edge.trade_details == "10K AAPL @ $150"
        assert edge.is_suspicious is True

    def test_edge_default_values(self):
        """Test edge with default values."""
        edge = RelationshipEdge(
            from_account="A",
            to_account="B",
            edge_type="ownership",
        )
        assert edge.trade_details is None
        assert edge.is_suspicious is False

    def test_valid_edge_types(self):
        """Test all valid edge types."""
        valid_types = ["trade", "ownership", "beneficial_owner"]
        for etype in valid_types:
            edge = RelationshipEdge(
                from_account="A",
                to_account="B",
                edge_type=etype,
            )
            assert edge.edge_type == etype


class TestRelationshipNetwork:
    """Tests for RelationshipNetwork model."""

    @pytest.fixture
    def sample_nodes(self):
        """Create sample nodes for testing."""
        return [
            RelationshipNode(
                account_id="ACC-001",
                beneficial_owner_id="BO-001",
                beneficial_owner_name="John Smith",
                relationship_type="direct",
                is_flagged=True,
            ),
            RelationshipNode(
                account_id="ACC-002",
                beneficial_owner_id="BO-001",
                beneficial_owner_name="John Smith",
                relationship_type="direct",
                is_flagged=True,
            ),
        ]

    @pytest.fixture
    def sample_edges(self):
        """Create sample edges for testing."""
        return [
            RelationshipEdge(
                from_account="ACC-001",
                to_account="ACC-002",
                edge_type="trade",
                is_suspicious=True,
            )
        ]

    def test_valid_network(self, sample_nodes, sample_edges):
        """Test creating a valid relationship network."""
        network = RelationshipNetwork(
            nodes=sample_nodes,
            edges=sample_edges,
            pattern_type="DIRECT_WASH",
            pattern_confidence=95,
            pattern_description="Same beneficial owner on both sides",
        )
        assert len(network.nodes) == 2
        assert len(network.edges) == 1
        assert network.pattern_type == "DIRECT_WASH"
        assert network.pattern_confidence == 95

    def test_network_pattern_types(self, sample_nodes, sample_edges):
        """Test valid pattern types."""
        valid_types = ["DIRECT_WASH", "LAYERED_WASH", "INTERMEDIARY_WASH", "NO_PATTERN"]
        for ptype in valid_types:
            network = RelationshipNetwork(
                nodes=sample_nodes,
                edges=sample_edges,
                pattern_type=ptype,
                pattern_confidence=50,
                pattern_description="Test",
            )
            assert network.pattern_type == ptype

    def test_get_flagged_accounts(self, sample_nodes, sample_edges):
        """Test getting flagged accounts."""
        network = RelationshipNetwork(
            nodes=sample_nodes,
            edges=sample_edges,
            pattern_type="DIRECT_WASH",
            pattern_confidence=95,
            pattern_description="Test",
        )
        flagged = network.get_flagged_accounts()
        assert "ACC-001" in flagged
        assert "ACC-002" in flagged

    def test_get_beneficial_owners(self, sample_nodes, sample_edges):
        """Test getting unique beneficial owners."""
        network = RelationshipNetwork(
            nodes=sample_nodes,
            edges=sample_edges,
            pattern_type="DIRECT_WASH",
            pattern_confidence=95,
            pattern_description="Test",
        )
        owners = network.get_beneficial_owners()
        assert len(owners) == 1
        assert "BO-001" in owners

    def test_has_same_beneficial_owner(self, sample_nodes, sample_edges):
        """Test checking for same beneficial owner."""
        network = RelationshipNetwork(
            nodes=sample_nodes,
            edges=sample_edges,
            pattern_type="DIRECT_WASH",
            pattern_confidence=95,
            pattern_description="Test",
        )
        assert network.has_same_beneficial_owner() is True


class TestTimingPattern:
    """Tests for TimingPattern model."""

    def test_valid_timing_pattern(self):
        """Test creating a valid timing pattern."""
        pattern = TimingPattern(
            time_delta_ms=502,
            time_delta_description="502ms between trades",
            market_phase="regular_session",
            liquidity_assessment="medium",
            is_pre_arranged=True,
            pre_arrangement_confidence=85,
            timing_analysis="Trades occurred within milliseconds suggesting pre-arrangement",
        )
        assert pattern.time_delta_ms == 502
        assert pattern.is_pre_arranged is True
        assert pattern.pre_arrangement_confidence == 85
        assert pattern.liquidity_assessment == "medium"

    def test_valid_market_phases(self):
        """Test valid market phases."""
        valid_phases = [
            "pre_market", "opening_auction", "regular_session",
            "closing_auction", "after_hours", "unknown"
        ]
        for phase in valid_phases:
            pattern = TimingPattern(
                time_delta_ms=1000,
                time_delta_description="1 second",
                market_phase=phase,
                liquidity_assessment="high",
                is_pre_arranged=False,
                pre_arrangement_confidence=0,
                timing_analysis="Test",
            )
            assert pattern.market_phase == phase

    def test_valid_liquidity_assessments(self):
        """Test valid liquidity assessment values."""
        valid_assessments = ["high", "medium", "low", "very_low"]
        for assessment in valid_assessments:
            pattern = TimingPattern(
                time_delta_ms=1000,
                time_delta_description="1 second",
                market_phase="regular_session",
                liquidity_assessment=assessment,
                is_pre_arranged=False,
                pre_arrangement_confidence=0,
                timing_analysis="Test",
            )
            assert pattern.liquidity_assessment == assessment


class TestTradeFlow:
    """Tests for TradeFlow model."""

    def test_valid_trade_flow(self):
        """Test creating a valid trade flow."""
        flow = TradeFlow(
            sequence_number=1,
            account_id="ACC-001",
            side="BUY",
            quantity=1000,
            price=150.0,
            timestamp="2024-01-15T10:30:00Z",
            counterparty_account="ACC-002",
        )
        assert flow.sequence_number == 1
        assert flow.account_id == "ACC-001"
        assert flow.side == "BUY"
        assert flow.quantity == 1000

    def test_trade_flow_optional_counterparty(self):
        """Test trade flow with optional counterparty."""
        flow = TradeFlow(
            sequence_number=1,
            account_id="A",
            side="SELL",
            quantity=100,
            price=10.0,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert flow.counterparty_account is None

    def test_valid_trade_sides(self):
        """Test valid trade sides."""
        for side in ["BUY", "SELL"]:
            flow = TradeFlow(
                sequence_number=1,
                account_id="A",
                side=side,
                quantity=100,
                price=10.0,
                timestamp="2024-01-01T00:00:00Z",
            )
            assert flow.side == side


class TestCounterpartyPattern:
    """Tests for CounterpartyPattern model."""

    @pytest.fixture
    def sample_trade_flows(self):
        """Create sample trade flows."""
        return [
            TradeFlow(
                sequence_number=1,
                account_id="ACC-001",
                side="BUY",
                quantity=100,
                price=10.0,
                timestamp="2024-01-01T10:00:00Z",
            ),
            TradeFlow(
                sequence_number=2,
                account_id="ACC-002",
                side="SELL",
                quantity=100,
                price=10.0,
                timestamp="2024-01-01T10:00:01Z",
            ),
        ]

    def test_valid_counterparty_pattern(self, sample_trade_flows):
        """Test creating a valid counterparty pattern."""
        pattern = CounterpartyPattern(
            trade_flow=sample_trade_flows,
            is_circular=False,
            is_offsetting=True,
            same_beneficial_owner=True,
            economic_purpose_identified=False,
        )
        assert len(pattern.trade_flow) == 2
        assert pattern.is_circular is False
        assert pattern.is_offsetting is True
        assert pattern.same_beneficial_owner is True

    def test_counterparty_pattern_with_intermediaries(self, sample_trade_flows):
        """Test pattern with intermediary accounts."""
        pattern = CounterpartyPattern(
            trade_flow=sample_trade_flows,
            is_circular=True,
            is_offsetting=True,
            same_beneficial_owner=True,
            intermediary_accounts=["ACC-003", "ACC-004"],
            economic_purpose_identified=False,
        )
        assert len(pattern.intermediary_accounts) == 2

    def test_counterparty_pattern_with_economic_purpose(self, sample_trade_flows):
        """Test pattern with economic purpose."""
        pattern = CounterpartyPattern(
            trade_flow=sample_trade_flows,
            is_circular=False,
            is_offsetting=True,
            same_beneficial_owner=False,
            economic_purpose_identified=True,
            economic_purpose_description="Market making activity for client hedging",
        )
        assert pattern.economic_purpose_identified is True
        assert "Market making" in pattern.economic_purpose_description


class TestHistoricalPatternSummary:
    """Tests for HistoricalPatternSummary model."""

    def test_valid_historical_summary(self):
        """Test creating a valid historical pattern summary."""
        summary = HistoricalPatternSummary(
            pattern_count=5,
            time_window_days=30,
            average_frequency="0.17 per day",
            pattern_trend="increasing",
            historical_analysis="Pattern has been increasing over the past 30 days",
        )
        assert summary.pattern_count == 5
        assert summary.time_window_days == 30
        assert summary.pattern_trend == "increasing"

    def test_valid_pattern_trends(self):
        """Test valid pattern trend values."""
        valid_trends = ["increasing", "stable", "decreasing", "new"]
        for trend in valid_trends:
            summary = HistoricalPatternSummary(
                pattern_count=1,
                time_window_days=30,
                average_frequency="0.03 per day",
                pattern_trend=trend,
                historical_analysis="Test",
            )
            assert summary.pattern_trend == trend


class TestWashTradeDecision:
    """Tests for WashTradeDecision model."""

    @pytest.fixture
    def sample_network(self):
        """Create a sample relationship network."""
        nodes = [
            RelationshipNode(
                account_id="ACC-001",
                beneficial_owner_id="BO-001",
                beneficial_owner_name="John Smith",
                relationship_type="direct",
                is_flagged=True,
            ),
            RelationshipNode(
                account_id="ACC-002",
                beneficial_owner_id="BO-001",
                beneficial_owner_name="John Smith",
                relationship_type="direct",
                is_flagged=True,
            ),
        ]
        edges = [
            RelationshipEdge(
                from_account="ACC-001",
                to_account="ACC-002",
                edge_type="trade",
                is_suspicious=True,
            )
        ]
        return RelationshipNetwork(
            nodes=nodes,
            edges=edges,
            pattern_type="DIRECT_WASH",
            pattern_confidence=95,
            pattern_description="Direct wash via same BO",
        )

    @pytest.fixture
    def sample_timing(self):
        """Create a sample timing pattern."""
        return TimingPattern(
            time_delta_ms=502,
            time_delta_description="502ms",
            market_phase="regular_session",
            liquidity_assessment="medium",
            is_pre_arranged=True,
            pre_arrangement_confidence=90,
            timing_analysis="Test timing analysis",
        )

    @pytest.fixture
    def sample_counterparty(self):
        """Create a sample counterparty pattern."""
        flows = [
            TradeFlow(
                sequence_number=1,
                account_id="ACC-001",
                side="BUY",
                quantity=1000,
                price=100.0,
                timestamp="2024-01-15T10:00:00Z",
            ),
            TradeFlow(
                sequence_number=2,
                account_id="ACC-002",
                side="SELL",
                quantity=1000,
                price=100.0,
                timestamp="2024-01-15T10:00:00.502Z",
            ),
        ]
        return CounterpartyPattern(
            trade_flow=flows,
            is_circular=False,
            is_offsetting=True,
            same_beneficial_owner=True,
            economic_purpose_identified=False,
        )

    @pytest.fixture
    def sample_historical(self):
        """Create a sample historical summary."""
        return HistoricalPatternSummary(
            pattern_count=3,
            time_window_days=90,
            average_frequency="0.03 per day",
            pattern_trend="stable",
            historical_analysis="Pattern has been stable",
        )

    @pytest.fixture
    def minimal_decision(self, sample_network, sample_timing, sample_counterparty, sample_historical):
        """Create a minimal valid WashTradeDecision."""
        return WashTradeDecision(
            alert_id="WT-TEST-001",
            determination="ESCALATE",
            genuine_alert_confidence=85,
            false_positive_confidence=15,
            key_findings=["Same beneficial owner", "Millisecond timing"],
            favorable_indicators=["Clear wash pattern"],
            risk_mitigating_factors=[],
            reasoning_narrative=(
                "This is a test reasoning narrative for wash trade analysis. The analysis shows "
                "clear evidence of wash trading activity with same beneficial owner on both sides "
                "of the trades, sub-second timing between trades, and no legitimate economic purpose."
            ),
            similar_precedent="Similar to WT-2023-100",
            relationship_network=sample_network,
            timing_patterns=sample_timing,
            counterparty_pattern=sample_counterparty,
            historical_patterns=sample_historical,
            volume_impact_percentage=8.5,
            beneficial_ownership_match=True,
            economic_purpose_identified=False,
            regulatory_flags=["MAS_SFA_S197"],
            recommended_action="ESCALATE",
        )

    def test_valid_wash_trade_decision(self, minimal_decision):
        """Test creating a valid wash trade decision."""
        assert minimal_decision.alert_id == "WT-TEST-001"
        assert minimal_decision.alert_type == "WASH_TRADE"
        assert minimal_decision.determination == "ESCALATE"
        assert minimal_decision.genuine_alert_confidence == 85
        assert minimal_decision.beneficial_ownership_match is True

    def test_determination_values(self, minimal_decision):
        """Test valid determination values."""
        valid_determinations = ["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"]
        for det in valid_determinations:
            decision = minimal_decision.model_copy(update={"determination": det})
            assert decision.determination == det

    def test_recommended_action_values(self, minimal_decision):
        """Test valid recommended action values."""
        valid_actions = ["ESCALATE", "CLOSE", "MONITOR", "REQUEST_MORE_DATA"]
        for action in valid_actions:
            decision = minimal_decision.model_copy(update={"recommended_action": action})
            assert decision.recommended_action == action

    def test_data_gaps_optional(self, minimal_decision):
        """Test data_gaps is optional with default empty list."""
        assert minimal_decision.data_gaps == []

        decision = minimal_decision.model_copy(
            update={"data_gaps": ["Missing account history"]}
        )
        assert len(decision.data_gaps) == 1

    def test_get_regulatory_summary(self, minimal_decision):
        """Test regulatory summary generation."""
        summary = minimal_decision.get_regulatory_summary()
        assert "Singapore MAS SFA Section 197" in summary

    def test_is_high_confidence_violation(self, minimal_decision):
        """Test high confidence violation detection."""
        assert minimal_decision.is_high_confidence_violation() is True

        low_confidence = minimal_decision.model_copy(
            update={"genuine_alert_confidence": 50}
        )
        assert low_confidence.is_high_confidence_violation() is False

        closed = minimal_decision.model_copy(
            update={"determination": "CLOSE"}
        )
        assert closed.is_high_confidence_violation() is False


class TestWashTradeFewShotExample:
    """Tests for WashTradeFewShotExample model."""

    def test_valid_few_shot_example(self):
        """Test creating a valid few-shot example."""
        example = WashTradeFewShotExample(
            id="WS-001",
            title="Direct Wash Trade - Same BO",
            jurisdiction="Singapore",
            regulation="MAS SFA Section 197",
            scenario={
                "accounts": "Two trading accounts under same beneficial owner",
                "pattern": "Offsetting trades within milliseconds",
            },
            determination="ESCALATE",
            reasoning="Clear wash trade pattern with same BO control",
            key_factors=["Same beneficial owner", "Sub-second timing"],
        )
        assert example.id == "WS-001"
        assert example.jurisdiction == "Singapore"
        assert example.determination == "ESCALATE"
        assert len(example.key_factors) == 2


class TestWashTradeFewShotCollection:
    """Tests for WashTradeFewShotCollection model."""

    def test_valid_collection(self):
        """Test creating a valid collection of examples."""
        examples = [
            WashTradeFewShotExample(
                id="WS-001",
                title="Test Case 1",
                jurisdiction="Singapore",
                regulation="MAS SFA Section 197",
                scenario={"test": "value"},
                determination="ESCALATE",
                reasoning="Test reasoning",
                key_factors=["Factor 1"],
            ),
        ]
        collection = WashTradeFewShotCollection(examples=examples)
        assert len(collection.examples) == 1

    def test_get_examples_text(self):
        """Test formatting examples as text."""
        examples = [
            WashTradeFewShotExample(
                id="WS-001",
                title="Test Case 1",
                jurisdiction="Singapore",
                regulation="MAS SFA Section 197",
                scenario={"pattern": "direct wash"},
                determination="ESCALATE",
                reasoning="Test reasoning",
                key_factors=["Factor 1"],
            ),
        ]
        collection = WashTradeFewShotCollection(examples=examples)
        text = collection.get_examples_text()

        assert "WS-001" in text
        assert "Singapore" in text
        assert "ESCALATE" in text
        assert "Test reasoning" in text


class TestModelSerialization:
    """Test model serialization and deserialization."""

    def test_wash_trade_decision_to_dict(self):
        """Test WashTradeDecision can be serialized to dict."""
        nodes = [
            RelationshipNode(
                account_id="A",
                beneficial_owner_id="BO-1",
                beneficial_owner_name="Test",
                relationship_type="direct",
            )
        ]
        edges = [
            RelationshipEdge(
                from_account="A",
                to_account="A",
                edge_type="ownership",
            )
        ]
        network = RelationshipNetwork(
            nodes=nodes,
            edges=edges,
            pattern_type="NO_PATTERN",
            pattern_confidence=0,
            pattern_description="No pattern",
        )
        timing = TimingPattern(
            time_delta_ms=0,
            time_delta_description="N/A",
            market_phase="unknown",
            liquidity_assessment="high",
            is_pre_arranged=False,
            pre_arrangement_confidence=0,
            timing_analysis="No analysis",
        )
        flows = [
            TradeFlow(
                sequence_number=1,
                account_id="A",
                side="BUY",
                quantity=100,
                price=10.0,
                timestamp="2024-01-01T00:00:00Z",
            ),
            TradeFlow(
                sequence_number=2,
                account_id="A",
                side="SELL",
                quantity=100,
                price=10.0,
                timestamp="2024-01-01T00:00:01Z",
            ),
        ]
        counterparty = CounterpartyPattern(
            trade_flow=flows,
            is_circular=False,
            is_offsetting=False,
            same_beneficial_owner=False,
            economic_purpose_identified=True,
        )
        historical = HistoricalPatternSummary(
            pattern_count=0,
            time_window_days=30,
            average_frequency="0 per day",
            pattern_trend="new",
            historical_analysis="No history",
        )

        decision = WashTradeDecision(
            alert_id="WT-001",
            determination="CLOSE",
            genuine_alert_confidence=20,
            false_positive_confidence=80,
            key_findings=["Licensed market maker activity with proper disclosure"],
            favorable_indicators=[],
            risk_mitigating_factors=["Market maker"],
            reasoning_narrative=(
                "This appears to be a false positive. The trading activity is consistent with "
                "licensed market maker operations, with proper regulatory disclosure and client "
                "authorization. There is a clear economic purpose for the trades and they are "
                "part of normal hedging operations. No suspicious pattern detected."
            ),
            similar_precedent="None",
            relationship_network=network,
            timing_patterns=timing,
            counterparty_pattern=counterparty,
            historical_patterns=historical,
            volume_impact_percentage=0.0,
            beneficial_ownership_match=False,
            economic_purpose_identified=True,
            regulatory_flags=[],
            recommended_action="CLOSE",
        )

        data = decision.model_dump()
        assert isinstance(data, dict)
        assert data["alert_id"] == "WT-001"
        assert data["alert_type"] == "WASH_TRADE"
        assert data["determination"] == "CLOSE"
