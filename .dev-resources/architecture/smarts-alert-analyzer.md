# SMARTS Alert False Positive Analyzer - Architecture Document

**Version:** 1.0
**Status:** POC
**Last Updated:** 2025-11-29

---

## Table of Contents

1. [Overview](#overview)
2. [Core Objective](#core-objective)
3. [System Architecture](#system-architecture)
4. [Agent Design](#agent-design)
5. [Tools Specification](#tools-specification)
6. [Few-Shot Examples Strategy](#few-shot-examples-strategy)
7. [Data Sources](#data-sources)
8. [Output Specification](#output-specification)
9. [Configuration](#configuration)
10. [Project Structure](#project-structure)
11. [Investigation Workflow](#investigation-workflow)
12. [Design Decisions](#design-decisions)

---

## Overview

This system is an intelligent compliance filter that analyzes SMARTS surveillance alerts to reduce false positive rates before escalating to human compliance analysts. It uses a fully agentic LLM-based approach with no hardcoded scoring weights.

### Key Characteristics

- **POC Phase**: Minimalistic, lean architecture
- **Fully Agentic**: Pure LLM reasoning without deterministic scoring
- **Adaptable**: Few-shot examples in external JSON file (no code changes for tuning)
- **Fail-Fast**: No graceful degradation; errors crash loudly for immediate debugging

---

## Core Objective

Reduce false positive rates by intelligently analyzing trading context before escalating alerts to human compliance analysts.

### Decision Outcomes

| Determination | Condition | Action |
|---------------|-----------|--------|
| `ESCALATE` | High confidence of genuine insider trading | Route to compliance analyst |
| `CLOSE` | High confidence of false positive | Auto-close with documentation |
| `NEEDS_HUMAN_REVIEW` | Conflicting signals, cannot decide | Route for human judgment |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT                                    │
│                      alert.xml                                   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LANGGRAPH AGENT                              │
│                                                                  │
│  TOOLS (each calls LLM internally for interpretation):           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ read_alert → query_trader_history → query_trader_profile │    │
│  │ query_market_news → query_market_data → query_peer_trades│    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              REASONING (with few-shot examples)          │    │
│  │                                                          │    │
│  │  "Compare this case to precedents..."                    │    │
│  │  "Trader baseline shows X, market context shows Y..."    │    │
│  │  "This most resembles Example 2 because..."              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              STRUCTURED OUTPUT (Pydantic)                │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         OUTPUT                                   │
│  resources/reports/decision_{alert_id}.json                      │
│  + audit_log.jsonl                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Design

### Architecture Pattern

- **Single Agent**: One LangGraph agent with multiple tools
- **Framework**: LangGraph
- **Execution Mode**: Synchronous (simple for POC)

### Reasoning Approach

The agent uses a **"Case Law" approach** where few-shot examples serve as legal precedents:

1. Agent gathers evidence via tools
2. Agent receives all tool outputs + few-shot examples
3. Agent compares current case to example precedents
4. Agent produces narrative reasoning explaining the comparison
5. Agent makes holistic judgment based on pattern matching

### Why Not Hardcoded Scores?

| Aspect | Hardcoded Scores | Agentic Reasoning |
|--------|------------------|-------------------|
| Adaptation | Requires code changes | Add few-shot examples |
| Learning | Cannot improve from examples | Learns from new precedents |
| Reasoning | Sum of weights | Narrative comparison |
| Feedback loop | Recalibrate weights manually | Add new examples to JSON |

---

## Tools Specification

Each tool:
1. Reads from data source (file)
2. Calls LLM internally to interpret unstructured data
3. Returns **insight** (not raw data) to the main agent

### Tool Definitions

| Tool | Input | Data Source | Returns |
|------|-------|-------------|---------|
| `read_alert` | - | alert.xml | Full XML content for agent to parse |
| `query_trader_history` | trader_id, symbol, trade_date | trader_history.csv | LLM-interpreted baseline analysis |
| `query_trader_profile` | trader_id | trader_profiles.csv | LLM-interpreted access/role assessment |
| `query_market_news` | symbol, date_range | market_news.txt | LLM-interpreted news timeline |
| `query_market_data` | symbol, date_range | market_data.csv | LLM-interpreted volatility/price analysis |
| `query_peer_trades` | symbol, date_range | peer_trades.csv | LLM-interpreted peer activity comparison |

### Tool Output Examples

```
query_trader_history(trader_id="T001", symbol="ACME", trade_date="2024-03-15")
→ "This trader typically trades 5,000 shares/day in tech sector.
   The flagged trade of 50,000 shares in healthcare is 10x their
   normal volume and a sector they've never touched in 12 months
   of history."

query_market_news(symbol="ACME", date_range="2024-03-08 to 2024-03-22")
→ "No public news about ACME before March 15. M&A announcement
   came March 16 at 9am EST. No analyst coverage or rumors found
   in the lookback period. First mention was the official press release."
```

---

## Few-Shot Examples Strategy

### Storage

- **Location**: `test_data/few_shot_examples.json`
- **Format**: JSON array of example cases
- **Adaptation**: Edit JSON file to tune behavior (no code changes)

### Example Structure

```json
{
  "examples": [
    {
      "id": "ex_001",
      "scenario": "genuine_clear",
      "alert_summary": "Back-office employee, never traded healthcare, 50K shares 36hrs before M&A",
      "trader_baseline": "Trades tech sector only, avg 2K shares/day, no healthcare history",
      "market_context": "No public news, no analyst coverage, announcement next day",
      "peer_activity": "No other traders bought this symbol in the period",
      "determination": "ESCALATE",
      "reasoning": "Classic pre-announcement pattern. Trader has no legitimate reason to trade this sector at 25x normal volume with no public information available. Isolated trading increases suspicion."
    }
  ]
}
```

### Scenario Coverage (5-6 examples)

| ID | Scenario | Determination | Purpose |
|----|----------|---------------|---------|
| ex_001 | Clear genuine insider trading | ESCALATE | Obvious red flags |
| ex_002 | Clear false positive | CLOSE | Obvious innocence |
| ex_003 | Subtle genuine case | ESCALATE | Indirect information leak |
| ex_004 | Subtle false positive | CLOSE | Coincidental timing |
| ex_005 | Ambiguous/conflicting | NEEDS_HUMAN_REVIEW | Mixed signals |
| ex_006 | (Optional) Edge case | Varies | Additional nuance |

---

## Data Sources

### POC Data Strategy

All data sources are local files for POC phase:

```
test_data/
├── alerts/
│   ├── alert_genuine.xml        # Clear insider trading scenario
│   ├── alert_false_positive.xml # Clear false positive scenario
│   └── alert_ambiguous.xml      # Edge case scenario
├── trader_history.csv           # trader_id, date, symbol, side, qty, price
├── trader_profiles.csv          # trader_id, name, role, department, restrictions
├── market_news.txt              # Free-form timestamped news items
├── market_data.csv              # symbol, date, open, high, low, close, volume, vix
├── peer_trades.csv              # Same schema as trader_history, different traders
└── few_shot_examples.json       # 5-6 precedent examples
```

### Data Schemas

**trader_history.csv**
```csv
trader_id,date,symbol,side,qty,price,sector
T001,2024-03-01,MSFT,BUY,1000,410.50,TECH
T001,2024-03-05,AAPL,SELL,500,175.25,TECH
```

**trader_profiles.csv**
```csv
trader_id,name,role,department,access_level,restrictions
T001,John Smith,PORTFOLIO_MANAGER,Equities,HIGH,None
T002,Jane Doe,BACK_OFFICE,Operations,LOW,No trading allowed
```

**market_news.txt** (free-form)
```
2024-03-15 09:30 - Reuters: TechCorp announces Q1 earnings beat, stock surges 15%
2024-03-14 14:00 - Bloomberg: Analysts upgrade TechCorp to "Buy" ahead of earnings
2024-03-10 11:00 - WSJ: TechCorp CEO hints at expansion in quarterly letter
```

**market_data.csv**
```csv
symbol,date,open,high,low,close,volume,vix
ACME,2024-03-14,100.00,102.50,99.00,101.75,1500000,18.5
ACME,2024-03-15,101.75,115.00,101.00,114.50,8500000,22.3
```

**peer_trades.csv**
```csv
trader_id,date,symbol,side,qty,price,trader_type
T101,2024-03-14,ACME,BUY,5000,101.00,INSTITUTIONAL
T102,2024-03-14,ACME,BUY,2000,101.50,RETAIL
```

### Role Definitions (for trader_profile)

| Role | Access Level | Description |
|------|--------------|-------------|
| `PORTFOLIO_MANAGER` | HIGH | Manages portfolios, high information access |
| `RESEARCH_ANALYST` | MEDIUM | Sector-specific research, some MNPI exposure |
| `TRADER` | LOW | Execution only, limited information access |
| `COMPLIANCE` | NONE | Sees alerts, no trading allowed |
| `BACK_OFFICE` | NONE | Operations, no information access |

---

## Output Specification

### Decision Output Schema (Pydantic)

```python
class TraderBaselineAnalysis(BaseModel):
    typical_volume: str
    typical_sectors: str
    typical_frequency: str
    deviation_assessment: str

class MarketContext(BaseModel):
    news_timeline: str
    volatility_assessment: str
    peer_activity_summary: str

class AlertDecision(BaseModel):
    alert_id: str
    determination: Literal["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"]
    genuine_alert_confidence: int  # 0-100
    false_positive_confidence: int  # 0-100

    key_findings: List[str]
    favorable_indicators: List[str]  # Reasons it might be genuine
    risk_mitigating_factors: List[str]  # Reasons it's likely false positive

    trader_baseline_analysis: TraderBaselineAnalysis
    market_context: MarketContext

    reasoning_narrative: str  # Human-readable explanation (2-4 paragraphs)
    similar_precedent: str  # Which few-shot example this resembles

    recommended_action: Literal["ESCALATE", "CLOSE", "MONITOR", "REQUEST_MORE_DATA"]
    data_gaps: List[str]  # Missing data that would improve analysis

    timestamp: datetime
```

### Output Location

- **Decision files**: `resources/reports/decision_{alert_id}.json`
- **Audit log**: `resources/reports/audit_log.jsonl` (append-only)

### Audit Log Entry

```json
{
  "timestamp": "2024-03-15T10:30:00Z",
  "alert_id": "ITA-2024-001847",
  "determination": "CLOSE",
  "confidence": {"genuine": 25, "false_positive": 85},
  "reasoning_summary": "Trading matches historical pattern...",
  "processing_time_seconds": 45.2
}
```

---

## Configuration

### Environment Variables

```bash
# .env.example

# LLM Provider: "openai" or "azure"
LLM_PROVIDER=openai

# OpenAI Configuration
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Azure OpenAI Configuration (if using Azure)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Data Paths
ALERT_FILE_PATH=test_data/alerts/alert.xml
DATA_DIR=test_data
OUTPUT_DIR=resources/reports

# Logging
LOG_LEVEL=INFO
```

### Config Loader Pattern

```python
# Config is loaded from environment variables
# Supports both OpenAI and Azure OpenAI
# No hardcoded values in source code
```

---

## Project Structure

```
alerts/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
│
├── src/
│   └── alerts/
│       ├── __init__.py
│       ├── main.py                 # Entry point
│       ├── config.py               # Config loader (env-based)
│       ├── agent.py                # LangGraph agent definition
│       ├── models.py               # Pydantic models for output
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py             # Base tool class with LLM helper
│       │   ├── alert_reader.py     # read_alert tool
│       │   ├── trader_history.py   # query_trader_history tool
│       │   ├── trader_profile.py   # query_trader_profile tool
│       │   ├── market_news.py      # query_market_news tool
│       │   ├── market_data.py      # query_market_data tool
│       │   └── peer_trades.py      # query_peer_trades tool
│       └── prompts/
│           ├── __init__.py
│           └── system_prompt.py    # Main agent system prompt
│
├── test_data/
│   ├── alerts/
│   │   ├── alert_genuine.xml
│   │   ├── alert_false_positive.xml
│   │   └── alert_ambiguous.xml
│   ├── trader_history.csv
│   ├── trader_profiles.csv
│   ├── market_news.txt
│   ├── market_data.csv
│   ├── peer_trades.csv
│   └── few_shot_examples.json
│
├── resources/
│   └── reports/
│
├── scripts/
│
└── tests/
    ├── __init__.py
    ├── test_agent.py
    ├── test_tools.py
    └── conftest.py
```

---

## Investigation Workflow

### Analyst Mental Model (What We're Automating)

1. **Check account trading history** (1 year lookback)
   - Has the trader been regularly trading this sector/stock?
   - Or is this out-of-the-blue unusual activity?

2. **Volume analysis**
   - Is this large volume relative to their baseline?
   - How does it compare to their typical daily volume?

3. **Sector analysis**
   - Is this a new sector for the trader?
   - Or do they regularly trade in this space?

4. **Market event correlation**
   - Was the trade just before a material announcement?
   - Earnings, M&A, regulatory news that would benefit the position?

5. **Synthesize and decide**
   - Does the pattern suggest insider knowledge?
   - Or is there a legitimate explanation?

### Agent Execution Flow

```
PHASE 1: EVIDENCE COLLECTION
├── Tool: read_alert()
│   → Extract alert_id, trader_id, symbol, trade_date, volume, rule_violated
│
├── Tool: query_trader_history(trader_id, symbol, trade_date)
│   → LLM interprets: "Baseline is X, this trade deviates by Y"
│
├── Tool: query_trader_profile(trader_id)
│   → LLM interprets: "Role is Z, access level suggests..."
│
├── Tool: query_market_news(symbol, date_range)
│   → LLM interprets: "News timeline shows..."
│
├── Tool: query_market_data(symbol, date_range)
│   → LLM interprets: "Volatility was high/low, price moved..."
│
└── Tool: query_peer_trades(symbol, date_range)
    → LLM interprets: "Other traders did/didn't trade similarly"

PHASE 2: REASONING
├── Agent receives all tool outputs
├── Agent loads few-shot examples from JSON
├── Agent compares current case to examples:
│   "This case resembles example X because..."
│   "Unlike example Y, this case has..."
└── Agent produces narrative reasoning

PHASE 3: OUTPUT
├── Structured decision (Pydantic model)
├── Write to resources/reports/decision_{alert_id}.json
└── Append to audit_log.jsonl
```

---

## Design Decisions

### Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent framework | LangGraph | Battle-tested, good tool support |
| Number of agents | Single agent | Simpler for POC, easier to debug |
| Tool LLM calls | Each tool calls LLM internally | Better accuracy through focused interpretation |
| Scoring approach | Pure LLM reasoning | Adaptable via few-shot examples without code changes |
| Few-shot storage | External JSON file | Easy to edit, no deployment needed |
| XML handling | Pass whole XML to agent | Avoid building parser for POC |
| Error handling | Fail-fast | Crash loudly, no silent failures |
| Confidence gap handling | Allow NEEDS_HUMAN_REVIEW | Agent can defer when genuinely conflicted |
| LLM provider | Config-driven (OpenAI/Azure) | Flexibility for enterprise deployment |
| Latency | Synchronous | Simple for POC, double-digit alert volume |

### Deferred Decisions (Future)

| Item | Notes |
|------|-------|
| XML extraction | Build selective extractor if XMLs become large |
| Feedback loop | Human analyst decisions flow back as new examples |
| Ground truth validation | Compare agent decisions to labeled historical data |
| Calendar events tool | Add if needed for earnings/event correlation |
| Internal communications | Add query_internal_communication tool later |
| Async processing | Convert to async if volume increases significantly |

---

## Appendix: Sample Alert XML Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
  <AlertID>ITA-2024-001847</AlertID>
  <AlertType>Pre-Announcement Trading</AlertType>
  <RuleViolated>MAR-03-001</RuleViolated>
  <GeneratedTimestamp>2024-03-16T10:30:00Z</GeneratedTimestamp>

  <Trader>
    <TraderID>T001</TraderID>
    <Name>John Smith</Name>
    <Department>Equities</Department>
  </Trader>

  <SuspiciousActivity>
    <Symbol>ACME</Symbol>
    <TradeDate>2024-03-15</TradeDate>
    <Side>BUY</Side>
    <Quantity>50000</Quantity>
    <Price>101.50</Price>
    <TotalValue>5075000</TotalValue>
  </SuspiciousActivity>

  <AnomalyIndicators>
    <AnomalyScore>87</AnomalyScore>
    <ConfidenceLevel>HIGH</ConfidenceLevel>
    <TemporalProximity>36 hours before M&amp;A announcement</TemporalProximity>
    <EstimatedProfit>675000</EstimatedProfit>
  </AnomalyIndicators>

  <RelatedEvent>
    <EventType>M&amp;A Announcement</EventType>
    <EventDate>2024-03-16</EventDate>
    <EventDescription>ACME Corp acquired by TechGiant for $150/share</EventDescription>
  </RelatedEvent>
</SMARTSAlert>
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-29 | Architecture Session | Initial architecture from brainstorming |
