"""Tests for SMARTS Alert Analyzer Pydantic models."""

import pytest
from datetime import datetime

from alerts.models import (
    AlertDecision,
    AlertSummary,
    FewShotExample,
    FewShotExamplesCollection,
    MarketContext,
    TraderBaselineAnalysis,
)


class TestTraderBaselineAnalysis:
    """Tests for TraderBaselineAnalysis model."""

    def test_creation(self):
        """Test model creation with valid data."""
        analysis = TraderBaselineAnalysis(
            typical_volume="5,000 shares/day",
            typical_sectors="Tech, Healthcare",
            typical_frequency="Daily",
            deviation_assessment="10x normal volume"
        )

        assert analysis.typical_volume == "5,000 shares/day"
        assert "Tech" in analysis.typical_sectors

    def test_json_serialization(self):
        """Test JSON serialization."""
        analysis = TraderBaselineAnalysis(
            typical_volume="1000",
            typical_sectors="Tech",
            typical_frequency="Weekly",
            deviation_assessment="Normal"
        )

        json_str = analysis.model_dump_json()
        assert "typical_volume" in json_str
        assert "1000" in json_str


class TestMarketContext:
    """Tests for MarketContext model."""

    def test_creation(self):
        """Test model creation with valid data."""
        context = MarketContext(
            news_timeline="No news before announcement",
            volatility_assessment="Low volatility",
            peer_activity_summary="Net selling"
        )

        assert "news" in context.news_timeline.lower()
        assert "volatility" in context.volatility_assessment.lower()


class TestAlertDecision:
    """Tests for AlertDecision model."""

    def test_creation_escalate(self):
        """Test creating an ESCALATE decision."""
        decision = AlertDecision(
            alert_id="TEST-001",
            determination="ESCALATE",
            genuine_alert_confidence=85,
            false_positive_confidence=15,
            key_findings=["Finding 1", "Finding 2"],
            favorable_indicators=["Indicator 1"],
            risk_mitigating_factors=["Factor 1"],
            trader_baseline_analysis=TraderBaselineAnalysis(
                typical_volume="1000",
                typical_sectors="Tech",
                typical_frequency="Daily",
                deviation_assessment="Anomalous"
            ),
            market_context=MarketContext(
                news_timeline="No news",
                volatility_assessment="Normal",
                peer_activity_summary="Isolated"
            ),
            reasoning_narrative="This is a detailed reasoning narrative that explains the decision. " * 5,
            similar_precedent="Resembles ex_001",
            recommended_action="ESCALATE"
        )

        assert decision.determination == "ESCALATE"
        assert decision.genuine_alert_confidence == 85
        assert decision.timestamp is not None

    def test_creation_close(self):
        """Test creating a CLOSE decision."""
        decision = AlertDecision(
            alert_id="TEST-002",
            determination="CLOSE",
            genuine_alert_confidence=20,
            false_positive_confidence=80,
            key_findings=["Normal trading pattern"],
            favorable_indicators=[],
            risk_mitigating_factors=["Public info available", "Consistent with history"],
            trader_baseline_analysis=TraderBaselineAnalysis(
                typical_volume="5000",
                typical_sectors="Tech",
                typical_frequency="Daily",
                deviation_assessment="Within normal range"
            ),
            market_context=MarketContext(
                news_timeline="Multiple analyst upgrades",
                volatility_assessment="Normal",
                peer_activity_summary="Net buying"
            ),
            reasoning_narrative="The trade is consistent with the trader's established pattern and publicly available information. " * 5,
            similar_precedent="Resembles ex_002",
            recommended_action="CLOSE"
        )

        assert decision.determination == "CLOSE"
        assert decision.false_positive_confidence == 80

    def test_confidence_validation(self):
        """Test confidence score validation."""
        # Valid confidence scores
        decision = AlertDecision(
            alert_id="TEST",
            determination="ESCALATE",
            genuine_alert_confidence=100,
            false_positive_confidence=0,
            key_findings=["Finding"],
            favorable_indicators=["Indicator"],
            risk_mitigating_factors=["Factor"],
            trader_baseline_analysis=TraderBaselineAnalysis(
                typical_volume="1000",
                typical_sectors="Tech",
                typical_frequency="Daily",
                deviation_assessment="Test"
            ),
            market_context=MarketContext(
                news_timeline="Test",
                volatility_assessment="Test",
                peer_activity_summary="Test"
            ),
            reasoning_narrative="Test reasoning " * 20,
            similar_precedent="Test",
            recommended_action="ESCALATE"
        )
        assert decision.genuine_alert_confidence == 100

        # Invalid confidence scores should raise validation error
        with pytest.raises(ValueError):
            AlertDecision(
                alert_id="TEST",
                determination="ESCALATE",
                genuine_alert_confidence=150,  # Invalid: > 100
                false_positive_confidence=0,
                key_findings=["Finding"],
                favorable_indicators=["Indicator"],
                risk_mitigating_factors=["Factor"],
                trader_baseline_analysis=TraderBaselineAnalysis(
                    typical_volume="1000",
                    typical_sectors="Tech",
                    typical_frequency="Daily",
                    deviation_assessment="Test"
                ),
                market_context=MarketContext(
                    news_timeline="Test",
                    volatility_assessment="Test",
                    peer_activity_summary="Test"
                ),
                reasoning_narrative="Test reasoning " * 20,
                similar_precedent="Test",
                recommended_action="ESCALATE"
            )

    def test_to_audit_entry(self):
        """Test conversion to audit log entry."""
        decision = AlertDecision(
            alert_id="TEST-001",
            determination="ESCALATE",
            genuine_alert_confidence=85,
            false_positive_confidence=15,
            key_findings=["Finding"],
            favorable_indicators=["Indicator"],
            risk_mitigating_factors=["Factor"],
            trader_baseline_analysis=TraderBaselineAnalysis(
                typical_volume="1000",
                typical_sectors="Tech",
                typical_frequency="Daily",
                deviation_assessment="Test"
            ),
            market_context=MarketContext(
                news_timeline="Test",
                volatility_assessment="Test",
                peer_activity_summary="Test"
            ),
            reasoning_narrative="Test reasoning narrative for the audit log entry. " * 10,
            similar_precedent="Test",
            recommended_action="ESCALATE"
        )

        audit_entry = decision.to_audit_entry()

        assert audit_entry["alert_id"] == "TEST-001"
        assert audit_entry["determination"] == "ESCALATE"
        assert audit_entry["confidence"]["genuine"] == 85
        assert "timestamp" in audit_entry

    def test_reasoning_narrative_min_length(self):
        """Test reasoning narrative minimum length validation."""
        with pytest.raises(ValueError):
            AlertDecision(
                alert_id="TEST",
                determination="ESCALATE",
                genuine_alert_confidence=85,
                false_positive_confidence=15,
                key_findings=["Finding"],
                favorable_indicators=["Indicator"],
                risk_mitigating_factors=["Factor"],
                trader_baseline_analysis=TraderBaselineAnalysis(
                    typical_volume="1000",
                    typical_sectors="Tech",
                    typical_frequency="Daily",
                    deviation_assessment="Test"
                ),
                market_context=MarketContext(
                    news_timeline="Test",
                    volatility_assessment="Test",
                    peer_activity_summary="Test"
                ),
                reasoning_narrative="Too short",  # Less than 100 chars
                similar_precedent="Test",
                recommended_action="ESCALATE"
            )


class TestFewShotExample:
    """Tests for FewShotExample model."""

    def test_creation(self):
        """Test creating a few-shot example."""
        example = FewShotExample(
            id="ex_001",
            scenario="genuine_clear",
            alert_summary="Test summary",
            trader_baseline="Test baseline",
            market_context="Test context",
            peer_activity="Test peer activity",
            determination="ESCALATE",
            reasoning="Test reasoning"
        )

        assert example.id == "ex_001"
        assert example.determination == "ESCALATE"

    def test_determination_validation(self):
        """Test determination field validation."""
        # Valid determinations
        for det in ["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"]:
            example = FewShotExample(
                id="test",
                scenario="test",
                alert_summary="test",
                trader_baseline="test",
                market_context="test",
                peer_activity="test",
                determination=det,
                reasoning="test"
            )
            assert example.determination == det

        # Invalid determination
        with pytest.raises(ValueError):
            FewShotExample(
                id="test",
                scenario="test",
                alert_summary="test",
                trader_baseline="test",
                market_context="test",
                peer_activity="test",
                determination="INVALID",
                reasoning="test"
            )


class TestFewShotExamplesCollection:
    """Tests for FewShotExamplesCollection model."""

    def test_creation(self, sample_few_shot_examples: dict):
        """Test creating a collection from dict."""
        collection = FewShotExamplesCollection(**sample_few_shot_examples)

        assert len(collection.examples) == 2
        assert collection.examples[0].id == "test_001"

    def test_get_examples_text(self, sample_few_shot_examples: dict):
        """Test formatting examples as text."""
        collection = FewShotExamplesCollection(**sample_few_shot_examples)

        text = collection.get_examples_text()

        assert "Precedent Cases" in text
        assert "test_001" in text
        assert "ESCALATE" in text
        assert "CLOSE" in text

    def test_empty_collection_rejected(self):
        """Test that empty collection raises validation error."""
        with pytest.raises(ValueError):
            FewShotExamplesCollection(examples=[])


class TestAlertSummary:
    """Tests for AlertSummary model."""

    def test_creation(self):
        """Test creating an alert summary."""
        summary = AlertSummary(
            alert_id="ITA-2024-001",
            alert_type="Pre-Announcement Trading",
            rule_violated="MAR-03-001",
            generated_timestamp="2024-03-16T10:30:00Z",
            trader_id="T001",
            trader_name="John Smith",
            trader_department="Operations",
            symbol="ACME",
            trade_date="2024-03-15",
            side="BUY",
            quantity=50000,
            price=101.50,
            total_value=5075000,
            anomaly_score=87,
            confidence_level="HIGH",
            temporal_proximity="36 hours before announcement",
            estimated_profit=675000,
            related_event_type="M&A Announcement",
            related_event_date="2024-03-16",
            related_event_description="Acquisition announcement"
        )

        assert summary.alert_id == "ITA-2024-001"
        assert summary.quantity == 50000
        assert summary.total_value == 5075000
