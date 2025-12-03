# Wash Trade Analyst Agent - Architecture Document

**Version:** 1.0
**Status:** Design Finalized
**Last Updated:** 2025-12-03
**Related:** [smarts-alert-analyzer.md](./smarts-alert-analyzer.md) (Insider Trading Agent)

---

## Table of Contents

1. [Overview](#overview)
2. [Design Decisions Summary](#design-decisions-summary)
3. [System Architecture](#system-architecture)
4. [Tool Architecture](#tool-architecture)
5. [Directory Structure](#directory-structure)
6. [Data Models](#data-models)
7. [Test Data Scenarios](#test-data-scenarios)
8. [Few-Shot Examples Strategy](#few-shot-examples-strategy)
9. [A2A Integration](#a2a-integration)
10. [HTML Report with Relationship Visualization](#html-report-with-relationship-visualization)
11. [Algorithm Specification](#algorithm-specification)
12. [Regulatory Framework](#regulatory-framework)
13. [Implementation Phases](#implementation-phases)

---

## Overview

The Wash Trade Analyst Agent is a specialized compliance agent that analyzes SMARTS surveillance alerts for potential wash trading activity. It follows the same architectural pattern as the Insider Trading Agent (two-tier LLM architecture with 6 tools) but with wash-trade-specific tools and reasoning.

### What is Wash Trading?

Wash trading occurs when the same beneficial owner is on both sides of a trade (directly or through related accounts), creating:
- Artificial trading volume
- False appearance of market liquidity
- Potential price manipulation

### Key Characteristics

- **Architecture Pattern**: Same as Insider Trading Agent (6 tools, LLM at each layer)
- **Tool Isolation**: Complete separation - no shared tools are modified
- **Regulatory Focus**: APAC-centric (Singapore MAS as primary)
- **Visualization**: SVG-based relationship network in HTML reports

---

## Design Decisions Summary

| Decision Point | Final Choice | Rationale |
|----------------|--------------|-----------|
| Architecture pattern | Same 6-tool pattern | Consistency, proven design |
| Tool reuse strategy | Shared `tools/common/` directory | Clean architecture, no circular imports |
| Directory structure | `src/alerts/agents/` with full refactor | Future-proof, allows easy addition of new agents |
| Relationship visualization | SVG-based graph | Professional look without JS complexity |
| Test scenarios | 4 scenarios (including layered) | Covers common evasion techniques |
| Regulatory focus | APAC-centric (Singapore primary) | Per stakeholder requirement |
| Decision model | Shared base + specialized extensions | DRY principle, type safety |
| A2A port | 10002 | Sequential after Insider Trading (10001) |

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                 Orchestrator Agent (Port 10000)                 │
│  (Reads alerts, determines type, routes to specialized agents)  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ A2A Protocol (JSON-RPC over HTTP)
            ┌───────────────┴───────────────┐
            │                               │
            ▼                               ▼
┌───────────────────────────┐   ┌───────────────────────────────┐
│   Insider Trading Agent   │   │     Wash Trade Agent          │
│      (Port 10001)         │   │       (Port 10002)            │
└───────────────────────────┘   └───────────────────────────────┘
```

### Wash Trade Agent Internal Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT                                    │
│                   wash_trade_alert.xml                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 WASH TRADE ANALYZER AGENT                        │
│                                                                  │
│  TOOLS (each calls LLM internally for interpretation):           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ AlertReader → AccountRelationships → RelatedAccountsHistory│   │
│  │ TradeTiming → CounterpartyAnalysis → MarketData            │   │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │        REASONING (with wash trade few-shot examples)     │    │
│  │                                                          │    │
│  │  "Compare to wash trade precedents..."                   │    │
│  │  "Account relationship shows X, timing pattern shows Y..."│   │
│  │  "This resembles Case 3 (layered wash) because..."       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           STRUCTURED OUTPUT (WashTradeDecision)          │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         OUTPUT                                   │
│  resources/reports/wash_trade_decision_{alert_id}.json           │
│  resources/reports/wash_trade_decision_{alert_id}.html           │
│  + audit_log.jsonl                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tool Architecture

### Tool Isolation Principle

**Critical**: Both agents must work independently without affecting each other. No shared tool is modified for agent-specific needs.

### Complete Tool Mapping

| Tool | Location | Used By | Description |
|------|----------|---------|-------------|
| **AlertReader** | `tools/common/` | Both | Generic SMARTS XML parsing |
| **TraderProfile** | `tools/common/` | Both | Account metadata lookup |
| **MarketData** | `tools/common/` | Both | Price/volume data analysis |
| **TraderHistory** | `tools/common/` | Insider Trading ONLY | Single trader history (UNCHANGED) |
| **MarketNews** | `agents/insider_trading/tools/` | Insider Trading ONLY | News correlation analysis |
| **PeerTrades** | `agents/insider_trading/tools/` | Insider Trading ONLY | Peer comparison |
| **AccountRelationships** | `agents/wash_trade/tools/` | Wash Trade ONLY | Beneficial ownership lookup |
| **TradeTiming** | `agents/wash_trade/tools/` | Wash Trade ONLY | Temporal pattern analysis |
| **CounterpartyAnalysis** | `agents/wash_trade/tools/` | Wash Trade ONLY | Circular trade detection |
| **RelatedAccountsHistory** | `agents/wash_trade/tools/` | Wash Trade ONLY | Multi-account trade history |

### Tool Comparison: Insider Trading vs Wash Trade

| Insider Trading Agent | Wash Trade Agent |
|-----------------------|------------------|
| AlertReader (common) | AlertReader (common) |
| TraderHistory (common) | RelatedAccountsHistory (wash-specific) |
| TraderProfile (common) | AccountRelationships (wash-specific) |
| MarketNews (insider-specific) | TradeTiming (wash-specific) |
| MarketData (common) | CounterpartyAnalysis (wash-specific) |
| PeerTrades (insider-specific) | MarketData (common) |

### Wash Trade Tool Specifications

#### 1. AccountRelationships

```
Purpose: Query beneficial ownership and find linked accounts

Input:
  - account_id: str (from alert)

Data Source: test_data/wash_trade/account_relationships.csv

Fields:
  - account_id
  - beneficial_owner_id
  - beneficial_owner_name
  - relationship_type (direct, family_trust, corporate, nominee)
  - linked_accounts[] (JSON array)
  - relationship_degree (1 = direct, 2 = through intermediary)

LLM Interpretation Output Example:
  "ACC-001 and ACC-002 share beneficial owner BO-123 (John Smith).
   Relationship: Family trust structure. Both accounts are 1st degree
   related through Smith Family Trust."
```

#### 2. RelatedAccountsHistory

```
Purpose: Query trade history for ALL related accounts (not just one trader)

Input:
  - account_ids: List[str] (from AccountRelationships output)
  - symbol: str (optional, from alert)
  - time_window: str (default: "30d")

Data Source: test_data/wash_trade/related_accounts_history.csv

Fields:
  - account_id
  - trade_date
  - trade_time
  - symbol
  - side (BUY/SELL)
  - quantity
  - price
  - counterparty_account
  - order_id

LLM Interpretation Output Example:
  "This is the 15th time in 30 days these accounts have executed
   offsetting trades within 1 minute. Pattern: ACC-001 buys, ACC-002
   sells same quantity within seconds. Historical frequency: 0.5
   occurrences per day. This pattern is anomalous."
```

#### 3. TradeTiming

```
Purpose: Analyze temporal patterns of the flagged trades

Input:
  - trade1_timestamp: str
  - trade2_timestamp: str
  - symbol: str

Data Source: Computed from alert + market_data.csv

Analysis:
  - Time delta between trades
  - Market phase (opening, regular, closing, after-hours)
  - Liquidity period assessment
  - Comparison to normal execution times

LLM Interpretation Output Example:
  "Trades executed at 14:32:15.123 and 14:32:15.625 (502ms apart).
   This is during a low-liquidity period (mid-afternoon lull).
   Time delta is consistent with pre-arranged execution. Normal
   execution gap for this volume would be 5-15 seconds."
```

#### 4. CounterpartyAnalysis

```
Purpose: Map trade flow and detect circular patterns

Input:
  - trades: List[Trade] (from alert and history)
  - account_relationships: Dict (from AccountRelationships)

Patterns Detected:
  - Direct wash: A → B where A and B have same beneficial owner
  - Layered wash: A → B → C → A (circular)
  - Intermediary wash: A → X → B where X is unrelated intermediary

LLM Interpretation Output Example:
  "Direct wash pattern detected: ACC-001 sold 10,000 AAPL to ACC-002.
   Both accounts controlled by beneficial owner BO-123. No intermediary
   obfuscation. Trade flow: ACC-001 → ACC-002 (same beneficial owner).
   Pattern classification: DIRECT_WASH with HIGH confidence."
```

---

## Directory Structure

### Target Structure (After Refactoring)

```
src/alerts/
├── __init__.py
├── main.py                          # CLI entry point
├── config.py                        # Environment configuration
│
├── models/
│   ├── __init__.py
│   ├── base.py                      # BaseAlertDecision
│   ├── insider_trading.py           # InsiderTradingDecision
│   └── wash_trade.py                # WashTradeDecision
│
├── tools/
│   └── common/                      # Shared tools (NEVER modified per-agent)
│       ├── __init__.py
│       ├── base.py                  # BaseTool class
│       ├── alert_reader.py          # Generic XML parsing
│       ├── trader_profile.py        # Account metadata
│       ├── trader_history.py        # Single trader history
│       └── market_data.py           # Price/volume data
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py                # Shared agent infrastructure
│   │
│   ├── insider_trading/
│   │   ├── __init__.py
│   │   ├── agent.py                 # InsiderTradingAnalyzerAgent
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── market_news.py
│   │   │   └── peer_trades.py
│   │   └── prompts/
│   │       └── system_prompt.py
│   │
│   └── wash_trade/
│       ├── __init__.py
│       ├── agent.py                 # WashTradeAnalyzerAgent
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── account_relationships.py
│       │   ├── related_accounts_history.py
│       │   ├── trade_timing.py
│       │   └── counterparty_analysis.py
│       └── prompts/
│           └── system_prompt.py
│
├── reports/
│   ├── __init__.py
│   ├── html_generator.py            # Base HTML generation
│   ├── insider_trading_report.py    # Insider trading specific
│   └── wash_trade_report.py         # Wash trade with SVG network
│
└── a2a/
    ├── __init__.py
    ├── insider_trading_executor.py
    ├── insider_trading_server.py
    ├── wash_trade_executor.py       # NEW
    ├── wash_trade_server.py         # NEW
    ├── orchestrator.py              # Updated for wash trade routing
    ├── orchestrator_executor.py
    ├── orchestrator_server.py
    └── test_client.py
```

### Test Data Structure

```
test_data/
├── alerts/
│   ├── alert_genuine.xml            # Insider trading
│   ├── alert_false_positive.xml     # Insider trading
│   ├── alert_ambiguous.xml          # Insider trading
│   └── wash_trade/
│       ├── wash_genuine.xml         # Clear wash trade
│       ├── wash_false_positive.xml  # Legitimate market making
│       ├── wash_ambiguous.xml       # Unclear case
│       └── wash_layered.xml         # A→B→C→A pattern
│
├── wash_trade/
│   ├── account_relationships.csv
│   └── related_accounts_history.csv
│
├── few_shot_examples.json           # Insider trading examples
├── wash_trade_few_shot_examples.json # Wash trade examples
├── trader_history.csv
├── trader_profiles.csv
├── market_news.txt
├── market_data.csv
└── peer_trades.csv
```

---

## Data Models

### Base Decision Model

```python
class BaseAlertDecision(BaseModel):
    """Common fields for all alert decisions"""
    alert_id: str
    alert_type: Literal["INSIDER_TRADING", "WASH_TRADE"]
    determination: Literal["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"]
    genuine_alert_confidence: int  # 0-100
    false_positive_confidence: int  # 0-100
    key_findings: List[str]
    favorable_indicators: List[str]  # Reasons suggesting genuine violation
    risk_mitigating_factors: List[str]  # Reasons suggesting false positive
    reasoning_narrative: str  # 2-4 paragraph explanation
    similar_precedent: Optional[str]  # Which few-shot example this resembles
    processing_timestamp: datetime
```

### Wash Trade Decision Model

```python
class RelationshipNode(BaseModel):
    """Node in the relationship network"""
    account_id: str
    beneficial_owner_id: str
    beneficial_owner_name: str
    relationship_type: str

class RelationshipEdge(BaseModel):
    """Edge representing a trade between accounts"""
    from_account: str
    to_account: str
    trade_details: str
    is_suspicious: bool

class RelationshipNetwork(BaseModel):
    """Network of account relationships and trade flows"""
    nodes: List[RelationshipNode]
    edges: List[RelationshipEdge]
    pattern_type: Literal["DIRECT_WASH", "LAYERED_WASH", "INTERMEDIARY_WASH", "NO_PATTERN"]
    pattern_confidence: int  # 0-100

class TimingPattern(BaseModel):
    """Temporal analysis of trades"""
    time_delta_ms: int
    market_phase: str
    liquidity_assessment: str
    is_pre_arranged: bool
    pre_arrangement_confidence: int  # 0-100

class WashTradeDecision(BaseAlertDecision):
    """Wash trade specific decision fields"""
    alert_type: Literal["WASH_TRADE"] = "WASH_TRADE"
    relationship_network: RelationshipNetwork
    timing_patterns: TimingPattern
    volume_impact_percentage: float
    beneficial_ownership_match: bool
    historical_pattern_count: int  # How many similar trades in history
    economic_purpose_identified: bool
    regulatory_flags: List[str]  # e.g., ["MAS_SFA_S197", "SFC_SFO_S274"]
```

---

## Test Data Scenarios

### Scenario 1: Genuine Wash Trade (`wash_genuine.xml`)

```
Description: Clear wash trade with same beneficial owner, offsetting
             trades within seconds, no economic purpose

Accounts: ACC-001 (Smith Family Trust), ACC-002 (Smith Holdings Ltd)
Beneficial Owner: BO-123 (John Smith)
Trade 1: ACC-001 BUYS 10,000 AAPL @ $150.00 at 14:32:15.123
Trade 2: ACC-002 SELLS 10,000 AAPL @ $150.00 at 14:32:15.625
Time Delta: 502ms
Volume Impact: 45% of daily volume

Expected Outcome: ESCALATE
Confidence: 95% genuine, 5% false positive

Key Indicators:
- Same beneficial owner
- Offsetting quantity
- Sub-second execution
- No price improvement
- No economic purpose
- Artificial volume creation
```

### Scenario 2: False Positive - Market Maker (`wash_false_positive.xml`)

```
Description: Legitimate market making activity with proper disclosure

Accounts: ACC-100 (Alpha Market Makers Pty), ACC-101 (Alpha Hedge Book)
Beneficial Owner: BO-500 (Alpha Financial Services)
Relationship: Licensed market maker with disclosed trading books
Trade 1: ACC-100 BUYS 5,000 TSLA @ $250.00 at 10:15:00.000
Trade 2: ACC-101 SELLS 5,000 TSLA @ $250.05 at 10:15:02.500
Time Delta: 2.5 seconds

Expected Outcome: CLOSE
Confidence: 10% genuine, 90% false positive

Key Indicators:
- Licensed market maker (disclosed)
- Separate trading books (hedge book vs market making book)
- Price improvement exists ($0.05)
- Within normal market making activity
- Economic purpose: inventory management
- Regulatory exemption applies
```

### Scenario 3: Ambiguous Case (`wash_ambiguous.xml`)

```
Description: Related but not same owner, 30-min gap, partial offset

Accounts: ACC-200 (Chen Investments), ACC-201 (Chen Family Office)
Beneficial Owners: BO-600 (Michael Chen), BO-601 (Sarah Chen - spouse)
Relationship: Spousal relationship (2nd degree)
Trade 1: ACC-200 BUYS 8,000 NVDA @ $450.00 at 09:30:00.000
Trade 2: ACC-201 SELLS 5,000 NVDA @ $452.00 at 10:00:00.000
Time Delta: 30 minutes
Offset: Partial (5,000 of 8,000)

Expected Outcome: NEEDS_HUMAN_REVIEW
Confidence: 45% genuine, 45% false positive

Key Indicators:
- Related but different beneficial owners (spousal)
- 30-minute gap (not sub-second)
- Partial offset only
- Price difference exists
- Could be coordinated or independent hedging
- Requires human judgment on intent
```

### Scenario 4: Layered Wash Trade (`wash_layered.xml`)

```
Description: Circular pattern through intermediary (A→B→C→A)

Accounts:
  - ACC-300 (Dragon Holdings)
  - ACC-301 (Phoenix Trading)
  - ACC-302 (Tiger Investments)
Beneficial Owner: BO-700 (Wei Zhang) controls all three
Pattern: ACC-300 → ACC-301 → ACC-302 → ACC-300

Trade 1: ACC-300 SELLS 15,000 BABA @ $85.00 to ACC-301 at 11:00:00.000
Trade 2: ACC-301 SELLS 15,000 BABA @ $85.00 to ACC-302 at 11:00:05.000
Trade 3: ACC-302 SELLS 15,000 BABA @ $85.00 to ACC-300 at 11:00:10.000

Expected Outcome: ESCALATE
Confidence: 98% genuine, 2% false positive

Key Indicators:
- Circular trade pattern confirmed
- Same beneficial owner for all accounts
- Same quantity, same price
- 10-second total cycle time
- Classic layered wash trade structure
- Attempted obfuscation through multiple accounts
- No economic purpose
```

---

## Few-Shot Examples Strategy

### File: `test_data/wash_trade_few_shot_examples.json`

The few-shot examples serve as "case law" - precedents the agent compares against. These are based on APAC regulatory frameworks.

### Example Structure

```json
{
  "examples": [
    {
      "id": "WS-001",
      "title": "Classic Same-Owner Wash Trade",
      "jurisdiction": "Singapore",
      "regulation": "MAS SFA Section 197",
      "scenario": {
        "accounts": ["ACC-A", "ACC-B"],
        "beneficial_owner": "Same person",
        "relationship": "Direct ownership",
        "trades": "Offsetting, sub-second, same price",
        "time_delta": "< 1 second",
        "volume_impact": "High (>20% daily volume)"
      },
      "determination": "ESCALATE",
      "reasoning": "Clear violation of SFA s197. Same beneficial owner on both sides creates false appearance of trading activity. No legitimate economic purpose. Sub-second execution indicates pre-arrangement.",
      "key_factors": [
        "Same beneficial owner",
        "No price improvement",
        "Sub-second execution",
        "High volume impact"
      ]
    },
    {
      "id": "WS-002",
      "title": "Licensed Market Maker Exemption",
      "jurisdiction": "Hong Kong",
      "regulation": "SFC SFO Section 274 Exemption",
      "scenario": {
        "accounts": ["Market Making Book", "Hedge Book"],
        "beneficial_owner": "Same entity (licensed)",
        "relationship": "Separate trading books",
        "trades": "Offsetting for inventory management",
        "time_delta": "Minutes",
        "volume_impact": "Normal for market maker"
      },
      "determination": "CLOSE",
      "reasoning": "Licensed market maker with proper disclosure. Trades between market making and hedge books are legitimate inventory management. Regulatory exemption under SFO applies.",
      "key_factors": [
        "Licensed market maker status",
        "Proper disclosure",
        "Legitimate economic purpose",
        "Regulatory exemption"
      ]
    },
    {
      "id": "WS-003",
      "title": "Family-Related Accounts Ambiguity",
      "jurisdiction": "Australia",
      "regulation": "ASIC Corporations Act s1041A",
      "scenario": {
        "accounts": ["Husband account", "Wife account"],
        "beneficial_owner": "Different but related",
        "relationship": "Spousal",
        "trades": "Partial offset, time gap",
        "time_delta": "30+ minutes",
        "volume_impact": "Moderate"
      },
      "determination": "NEEDS_HUMAN_REVIEW",
      "reasoning": "Spousal relationship creates suspicion but not certainty. Time gap and partial offset could indicate independent trading decisions. Requires investigation of communication records and trading intent.",
      "key_factors": [
        "Related but different owners",
        "Time gap exists",
        "Partial offset only",
        "Intent unclear"
      ]
    },
    {
      "id": "WS-004",
      "title": "Layered Circular Pattern",
      "jurisdiction": "Singapore",
      "regulation": "MAS SFA Section 197, 198",
      "scenario": {
        "accounts": ["Company A", "Company B", "Company C"],
        "beneficial_owner": "Same controlling shareholder",
        "relationship": "Corporate structure obfuscation",
        "trades": "Circular A→B→C→A",
        "time_delta": "Seconds between legs",
        "volume_impact": "Very high (artificial)"
      },
      "determination": "ESCALATE",
      "reasoning": "Sophisticated wash trade using layered corporate structure. Same beneficial owner controls all entities. Circular pattern designed to create artificial volume while shares return to origin. Clear market manipulation under SFA s197 and s198.",
      "key_factors": [
        "Circular trade pattern",
        "Same ultimate beneficial owner",
        "Corporate obfuscation attempt",
        "Shares return to origin"
      ]
    }
  ]
}
```

---

## A2A Integration

### Port Assignments

| Agent | Port | Endpoint |
|-------|------|----------|
| Orchestrator | 10000 | `http://localhost:10000` |
| Insider Trading | 10001 | `http://localhost:10001` |
| Wash Trade | 10002 | `http://localhost:10002` |

### Orchestrator Routing Logic

```python
def route_alert(alert_xml: str) -> str:
    """Determine which agent should handle this alert"""
    alert_type = parse_alert_type(alert_xml)

    routing_table = {
        "InsiderTrading": "http://localhost:10001",
        "WashTrade": "http://localhost:10002",
        # Future agents can be added here
    }

    return routing_table.get(alert_type, None)
```

### A2A Agent Card (Wash Trade)

```json
{
  "name": "Wash Trade Analyst",
  "description": "Analyzes SMARTS surveillance alerts for potential wash trading violations",
  "version": "1.0.0",
  "capabilities": {
    "input_types": ["application/xml"],
    "output_types": ["application/json"],
    "analysis_types": ["wash_trade_detection"]
  },
  "regulatory_frameworks": ["MAS_SFA", "SFC_SFO", "ASIC_CA", "FSA_FIEA"],
  "endpoints": {
    "analyze": "/tasks",
    "health": "/health",
    "agent_card": "/.well-known/agent.json"
  }
}
```

---

## HTML Report with Relationship Visualization

### SVG Network Diagram Specification

The wash trade HTML report includes an SVG-based relationship network visualization.

```
┌─────────────────────────────────────────────────────────────┐
│                 Relationship Network                         │
│                                                              │
│    ┌─────────┐         TRADE          ┌─────────┐           │
│    │ ACC-001 │ ──────────────────────▶│ ACC-002 │           │
│    │ (Smith  │   10K AAPL @ $150     │ (Smith  │           │
│    │  Trust) │                        │Holdings)│           │
│    └────┬────┘                        └────┬────┘           │
│         │                                  │                │
│         └──────────┐      ┌────────────────┘                │
│                    ▼      ▼                                 │
│              ┌──────────────┐                               │
│              │   BO-123     │                               │
│              │ John Smith   │                               │
│              │ (Beneficial  │                               │
│              │   Owner)     │                               │
│              └──────────────┘                               │
│                                                              │
│  Legend:                                                     │
│  ───▶ Trade flow    ─ ─▶ Ownership                          │
│  🔴 Flagged account  ⚪ Beneficial owner                     │
└─────────────────────────────────────────────────────────────┘
```

### Report Sections

1. **Alert Summary** - Basic alert metadata
2. **Determination Banner** - Color-coded (ESCALATE=red, CLOSE=green, REVIEW=yellow)
3. **Confidence Scores** - Progress bars for genuine/false positive
4. **Relationship Network** - SVG visualization
5. **Timing Analysis** - Timeline of trades
6. **Key Findings** - Bulleted list
7. **Regulatory Flags** - Applicable regulations
8. **Reasoning Narrative** - Full explanation
9. **Similar Precedent** - Which example this resembles

---

## Algorithm Specification

### WashTradeAnalyzerAgent Main Flow

```
INPUT: SMARTS WashTrade Alert XML

STEP 1: AlertReader (common tool)
├── Parse XML for Trade1, Trade2 (or TradeN for multi-leg)
├── Extract: accounts, symbols, quantities, prices, timestamps
└── LLM Output: "Two offsetting trades in AAPL, 10K shares each,
                0.5 seconds apart, accounts ACC-001 and ACC-002"

STEP 2: AccountRelationships (wash-specific tool)
├── Query account_relationships.csv for both accounts
├── Find beneficial owners, linked accounts, relationship types
├── Build initial relationship graph
└── LLM Output: "ACC-001 and ACC-002 share beneficial owner
                BO-123 (John Smith). Relationship: Family trust."

STEP 3: RelatedAccountsHistory (wash-specific tool)
├── Get historical trades for ALL related accounts
├── Look for pattern of offsetting trades
├── Calculate frequency and recurrence
└── LLM Output: "15th occurrence in 30 days. Average: 0.5/day.
                Pattern is anomalous compared to baseline."

STEP 4: TradeTiming (wash-specific tool)
├── Analyze temporal patterns of flagged trades
├── Compare to market activity, liquidity periods
├── Assess pre-arrangement probability
└── LLM Output: "502ms apart, low-liquidity period, pattern
                suggests pre-arrangement with 90% confidence."

STEP 5: CounterpartyAnalysis (wash-specific tool)
├── Map complete trade flow
├── Detect patterns: DIRECT_WASH, LAYERED_WASH, INTERMEDIARY_WASH
├── Calculate pattern confidence
└── LLM Output: "Direct wash pattern detected. ACC-001 → ACC-002,
                same beneficial owner. Pattern: DIRECT_WASH (HIGH)."

STEP 6: MarketData (common tool)
├── Check volume impact, price movement
├── Assess market manipulation evidence
└── LLM Output: "20K shares = 45% daily volume. Created artificial
                appearance of liquidity. Price unchanged."

FINAL: Agent LLM Reasoning
├── Compile all tool outputs
├── Compare to wash trade precedents (few-shot examples)
├── Apply APAC regulatory framework (MAS SFA, SFC SFO, etc.)
├── Consider: beneficial ownership, timing, volume, economic purpose
├── Generate WashTradeDecision with:
│   ├── relationship_network (for SVG visualization)
│   ├── timing_patterns
│   ├── regulatory_flags
│   └── reasoning_narrative
└── OUTPUT: WashTradeDecision + HTML Report
```

---

## Regulatory Framework

### Primary Jurisdiction: Singapore (MAS)

| Regulation | Description | Key Provisions |
|------------|-------------|----------------|
| **SFA Section 197** | False trading and market rigging | Prohibits trades that create false/misleading appearance of active trading |
| **SFA Section 198** | Market manipulation | Prohibits transactions to affect market price |
| **SFA Section 199** | Wash trades specifically | Prohibits matching orders without change in beneficial ownership |

### Secondary Jurisdictions

| Jurisdiction | Regulation | Description |
|--------------|------------|-------------|
| **Hong Kong (SFC)** | SFO Section 274 | Market misconduct - false trading |
| **Australia (ASIC)** | Corporations Act s1041A-C | Market manipulation provisions |
| **Japan (FSA)** | FIEA Article 159 | Wash trading prohibition |

### Red Flags for Detection

1. **Same beneficial owner** on both sides of trade
2. **Pre-arranged trades** - sub-second execution
3. **No change in beneficial ownership** after trade
4. **Artificial volume** - high percentage of daily volume
5. **No price improvement** - trades at same price
6. **Circular patterns** - A→B→C→A structures
7. **Low-liquidity timing** - trades during quiet periods
8. **Historical patterns** - repeated similar behavior

---

## Implementation Phases

### Phase 1: Refactoring (Prerequisite)

**Objective**: Restructure codebase for multi-agent support

Tasks:
1. Create `src/alerts/agents/` directory structure
2. Move insider trading code to `agents/insider_trading/`
3. Create `tools/common/` with shared tools
4. Create `models/` with base and specific decision models
5. Update all imports and references
6. Update A2A executors and servers
7. Ensure all existing tests pass
8. Update CLAUDE.md and documentation

### Phase 2: Wash Trade Agent Core

**Objective**: Implement the wash trade analyzer agent

Tasks:
1. Create `agents/wash_trade/agent.py` (WashTradeAnalyzerAgent)
2. Implement wash-trade-specific tools:
   - `AccountRelationships`
   - `RelatedAccountsHistory`
   - `TradeTiming`
   - `CounterpartyAnalysis`
3. Create `WashTradeDecision` Pydantic model
4. Create wash trade system prompt with APAC regulatory context
5. Write unit tests for all new tools

### Phase 3: Test Data

**Objective**: Create comprehensive test scenarios

Tasks:
1. Create wash trade alert XMLs (4 scenarios)
2. Create mock data files:
   - `account_relationships.csv`
   - `related_accounts_history.csv`
3. Create `wash_trade_few_shot_examples.json` with APAC examples
4. Validate data consistency across files

### Phase 4: Reports & A2A

**Objective**: Integrate reporting and A2A protocol

Tasks:
1. Extend HTML generator for SVG relationship network
2. Create `wash_trade_report.py` with visualization
3. Create `wash_trade_executor.py` (A2A executor)
4. Create `wash_trade_server.py` (port 10002)
5. Update orchestrator routing logic
6. Test A2A communication flow

### Phase 5: Testing & Documentation

**Objective**: Comprehensive testing and documentation

Tasks:
1. Unit tests for all new components
2. Integration tests for wash trade agent
3. End-to-end tests with all 4 scenarios
4. A2A protocol tests (orchestrator → wash trade)
5. Update README.md
6. Update CLAUDE.md with wash trade instructions

---

## Appendix: Data File Schemas

### account_relationships.csv

```csv
account_id,beneficial_owner_id,beneficial_owner_name,relationship_type,linked_accounts,relationship_degree
ACC-001,BO-123,John Smith,family_trust,"[""ACC-002"",""ACC-003""]",1
ACC-002,BO-123,John Smith,corporate,"[""ACC-001""]",1
ACC-100,BO-500,Alpha Financial Services,market_maker,"[""ACC-101""]",1
ACC-101,BO-500,Alpha Financial Services,hedge_book,"[""ACC-100""]",1
ACC-200,BO-600,Michael Chen,direct,"[""ACC-201""]",2
ACC-201,BO-601,Sarah Chen,spousal,"[""ACC-200""]",2
ACC-300,BO-700,Wei Zhang,corporate,"[""ACC-301"",""ACC-302""]",1
ACC-301,BO-700,Wei Zhang,corporate,"[""ACC-300"",""ACC-302""]",1
ACC-302,BO-700,Wei Zhang,corporate,"[""ACC-300"",""ACC-301""]",1
```

### related_accounts_history.csv

```csv
account_id,trade_date,trade_time,symbol,side,quantity,price,counterparty_account,order_id
ACC-001,2024-01-15,14:32:15.123,AAPL,BUY,10000,150.00,ACC-002,ORD-001
ACC-002,2024-01-15,14:32:15.625,AAPL,SELL,10000,150.00,ACC-001,ORD-002
ACC-001,2024-01-10,10:15:00.000,AAPL,BUY,5000,148.00,ACC-002,ORD-003
ACC-002,2024-01-10,10:15:01.200,AAPL,SELL,5000,148.00,ACC-001,ORD-004
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-03 | Claude | Initial architecture document |

---

*This document should be updated as implementation progresses and design decisions evolve.*
