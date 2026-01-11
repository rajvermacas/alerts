# Remove AlertReaderTool Architecture

**Version:** 1.0
**Status:** Approved
**Last Updated:** 2025-01-11
**Author:** Architecture Team

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Target Architecture](#target-architecture)
4. [AlertContext Schema](#alertcontext-schema)
5. [API Contract](#api-contract)
6. [Execution Flow](#execution-flow)
7. [Component Changes](#component-changes)
8. [SSE Event Changes](#sse-event-changes)
9. [Technology Stack](#technology-stack)
10. [Files Changed Summary](#files-changed-summary)
11. [Testing Strategy](#testing-strategy)
12. [Design Decisions](#design-decisions)

---

## Overview

This document describes the architectural changes to remove `AlertReaderTool` and shift alert context extraction to the Big Data Layer.

### Key Decisions

| Decision | Answer |
|----------|--------|
| LLM Narrative in AlertReaderTool | **Drop** - Other tools have their own LLM interpretation |
| Context Extraction Owner | **Big Data Layer** - Pure XML→JSON transformation |
| Backward Compatibility | **None** - Clean break, fail-fast philosophy |
| Synthetic Event | **Yes** - Emit `context_received` for UI consistency |
| AnomalyIndicators in AlertContext | **Excluded** - SMARTS pre-analysis, not raw data |

### Guiding Principle

**Big Data Layer = Pure XML→JSON transformation. No analysis. No computed fields.**

Only factual data present in the raw XML can be passed. The agent performs all analysis.

---

## Problem Statement

### Current State

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CURRENT ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BigDataSimulator                                                            │
│       │                                                                      │
│       │ AnalysisRequest {                                                    │
│       │   alert_xml: "<raw XML>",        ◀── DUPLICATE                      │
│       │   tool_data: {                                                       │
│       │     alert_reader: {xml},         ◀── DUPLICATE (same XML)           │
│       │     market_news: {txt},                                              │
│       │     ...                                                              │
│       │   }                                                                  │
│       │ }                                                                    │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  IT Agent                                                            │    │
│  │                                                                      │    │
│  │  Step 1: AlertReaderTool.execute()  ◀── BLOCKING (runs first)       │    │
│  │          ├─ LLM interprets XML      ◀── UNNECESSARY LLM call        │    │
│  │          └─ parse_alert_context()   ◀── Extracts trader_id, symbol  │    │
│  │                                                                      │    │
│  │  Step 2: Other 4 tools (parallel)                                   │    │
│  │          └─ Use context from Step 1                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  PROBLEMS:                                                                   │
│  ─────────                                                                   │
│  1. AlertReaderTool blocks parallel execution of other tools                │
│  2. LLM call for XML parsing is unnecessary (regex suffices)                │
│  3. alert_xml passed twice (in field AND in tool_data)                      │
│  4. Context extraction done in agent layer (wrong responsibility)           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Target State

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TARGET ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BigDataSimulator (or Production Big Data Layer)                            │
│       │                                                                      │
│       │ Parses XML → Structured AlertContext                                │
│       │ (regex-based, NO LLM)                                               │
│       │                                                                      │
│       │ AnalysisRequest {                                                    │
│       │   alert_context: {              ◀── STRUCTURED (replaces alert_xml) │
│       │     alert_id, trader, trade,                                        │
│       │     related_event                                                   │
│       │   },                                                                 │
│       │   tool_data: {                  ◀── NO alert_reader entry           │
│       │     market_news: {txt},                                              │
│       │     market_data: {csv},                                              │
│       │     ...                                                              │
│       │   }                                                                  │
│       │ }                                                                    │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  IT Agent                                                            │    │
│  │                                                                      │    │
│  │  Step 1: Read alert_context directly  ◀── NO tool, NO LLM           │    │
│  │          └─ Emit context_received event                             │    │
│  │          └─ Compute start_date, end_date internally                 │    │
│  │                                                                      │    │
│  │  Step 2: ALL 4 tools run in parallel  ◀── NO blocking step          │    │
│  │          ├─ market_news                                              │    │
│  │          ├─ market_data                                              │    │
│  │          ├─ trader_profile                                           │    │
│  │          └─ trader_history                                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  BENEFITS:                                                                   │
│  ─────────                                                                   │
│  1. No blocking step - all tools parallel from start                        │
│  2. No unnecessary LLM call for XML parsing                                 │
│  3. No duplicate data (alert_xml removed)                                   │
│  4. Clean separation: Big Data = data, Agent = analysis                     │
│  5. Faster analysis (removed 1 LLM call + blocking step)                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Target Architecture

### Responsibility Separation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BIG DATA LAYER                                        │
│                        ───────────────                                       │
│                                                                              │
│  Responsibility: XML → JSON (1:1 structure mapping)                         │
│                                                                              │
│  ✓ Parse XML tags to structured fields                                      │
│  ✓ Convert to AlertContext (Pydantic model)                                 │
│  ✓ Aggregate tool data (CSV, TXT from production systems)                  │
│  ✓ Determine agent_type from alert content                                  │
│                                                                              │
│  ✗ NO analysis of any kind                                                  │
│  ✗ NO computed fields (start_date, end_date)                               │
│  ✗ NO anomaly indicators (SMARTS pre-analysis)                             │
│  ✗ NO LLM calls                                                             │
│                                                                              │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   │ HTTP POST /api/analyze
                                   │ Body: AnalysisRequest
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR (Port 10000)                             │
│                        ─────────────────────────                             │
│                                                                              │
│  Responsibility: Routing only                                               │
│                                                                              │
│  ✓ Validate AnalysisRequest schema                                         │
│  ✓ Route to agent based on agent_type                                      │
│  ✓ Pass request unchanged                                                   │
│  ✓ Proxy SSE events to client                                              │
│                                                                              │
│  ✗ NO data transformation                                                   │
│  ✗ NO business logic                                                        │
│                                                                              │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   │ A2A JSON-RPC
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AGENT (IT: 10001, WT: 10002)                          │
│                        ────────────────────────────                          │
│                                                                              │
│  Responsibility: All analysis and reasoning                                 │
│                                                                              │
│  ✓ Read alert_context directly from request                                │
│  ✓ Compute date ranges (trade_date ± N days)                               │
│  ✓ Execute tools with injected data (parallel)                             │
│  ✓ LLM interpretation in each tool                                         │
│  ✓ Final synthesis (LLM reasoning over all insights)                       │
│  ✓ Emit SSE events (context_received, tool_*, analysis_complete)           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## AlertContext Schema

### Source XML Structure

Based on actual alert file (`test_data/alerts/alert_genuine.xml`):

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
    <Department>Operations</Department>
  </Trader>

  <SuspiciousActivity>
    <Symbol>ACME</Symbol>
    <TradeDate>2024-03-15</TradeDate>
    <Side>BUY</Side>
    <Quantity>50000</Quantity>
    <Price>101.50</Price>
    <TotalValue>5075000</TotalValue>
  </SuspiciousActivity>

  <AnomalyIndicators>           ← EXCLUDED (SMARTS analysis, not raw data)
    <AnomalyScore>87</AnomalyScore>
    <ConfidenceLevel>HIGH</ConfidenceLevel>
    <TemporalProximity>36 hours before M&A announcement</TemporalProximity>
    <EstimatedProfit>675000</EstimatedProfit>
  </AnomalyIndicators>

  <RelatedEvent>
    <EventType>M&A Announcement</EventType>
    <EventDate>2024-03-16</EventDate>
    <EventDescription>ACME Corp acquired by TechGiant for $150/share</EventDescription>
  </RelatedEvent>
</SMARTSAlert>
```

### Pydantic Models

**File**: `src/alerts/models/alert_context.py` (NEW)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  class Trader(BaseModel):                                                    │
│      """Maps to <Trader> in XML."""                                         │
│      trader_id: str              # <TraderID>                               │
│      name: str                   # <Name>                                   │
│      department: str             # <Department>                             │
│                                                                              │
│  class Trade(BaseModel):                                                     │
│      """Maps to <SuspiciousActivity> in XML."""                             │
│      symbol: str                 # <Symbol>                                 │
│      trade_date: date            # <TradeDate>                              │
│      side: Literal["BUY","SELL"] # <Side>                                   │
│      quantity: int               # <Quantity>                               │
│      price: Decimal              # <Price>                                  │
│      total_value: Decimal        # <TotalValue>                             │
│                                                                              │
│  class RelatedEvent(BaseModel):                                              │
│      """Maps to <RelatedEvent> in XML. Optional."""                         │
│      event_type: str             # <EventType>                              │
│      event_date: date            # <EventDate>                              │
│      description: str            # <EventDescription>                       │
│                                                                              │
│  class AlertContext(BaseModel):                                              │
│      """1:1 mapping from XML structure. No computed fields. No analysis.""" │
│                                                                              │
│      # Root attributes                                                       │
│      alert_id: str               # <AlertID>                                │
│      alert_type: str             # <AlertType>                              │
│      rule_violated: str          # <RuleViolated>                           │
│      generated_timestamp: datetime  # <GeneratedTimestamp>                  │
│                                                                              │
│      # Nested structures                                                     │
│      trader: Trader              # <Trader>                                 │
│      trade: Trade                # <SuspiciousActivity>                     │
│      related_event: Optional[RelatedEvent] = None  # <RelatedEvent>         │
│                                                                              │
│      # EXCLUDED (not passed from Big Data Layer):                           │
│      # - <AnomalyIndicators> entire section                                 │
│      #   - AnomalyScore                                                     │
│      #   - ConfidenceLevel                                                  │
│      #   - TemporalProximity                                                │
│      #   - EstimatedProfit                                                  │
│      # - start_date (computed by agent: trade_date - 30 days)              │
│      # - end_date (computed by agent: trade_date + 7 days)                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Contract

### Updated AnalysisRequest

**File**: `src/alerts/models/request.py`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BEFORE                                  AFTER                               │
│  ──────                                  ─────                               │
│                                                                              │
│  class AnalysisRequest:                  class AnalysisRequest:              │
│      alert_xml: str          ──────►         alert_context: AlertContext    │
│      agent_type: Literal[...]                agent_type: Literal[...]       │
│      tool_data: Dict[str, ToolInput]         tool_data: Dict[str, ToolInput]│
│                                                                              │
│  REQUIRED_TOOLS_BY_AGENT:               REQUIRED_TOOLS_BY_AGENT:            │
│                                                                              │
│  "insider_trading": {                    "insider_trading": {                │
│      "alert_reader": "xml",  ──────►         # REMOVED                      │
│      "market_news": "txt",                   "market_news": "txt",          │
│      "market_data": "csv",                   "market_data": "csv",          │
│      "trader_profile": "csv",                "trader_profile": "csv",       │
│      "trader_history": "csv",                "trader_history": "csv",       │
│  }                                       }                                   │
│                                                                              │
│  "wash_trade": {                         "wash_trade": {                     │
│      "alert_reader": "xml",  ──────►         # REMOVED                      │
│      "market_data": "csv",                   "market_data": "csv",          │
│      "account_relationships": "csv",         "account_relationships": "csv",│
│      ...                                     ...                            │
│  }                                       }                                   │
│                                                                              │
│  TOOL_FORMATS:                           TOOL_FORMATS:                       │
│      "alert_reader": "xml",  ──────►         # REMOVED                      │
│      "market_news": "txt",                   "market_news": "txt",          │
│      ...                                     ...                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Request Payload Example

```json
{
  "alert_context": {
    "alert_id": "ITA-2024-001847",
    "alert_type": "Pre-Announcement Trading",
    "rule_violated": "MAR-03-001",
    "generated_timestamp": "2024-03-16T10:30:00Z",

    "trader": {
      "trader_id": "T001",
      "name": "John Smith",
      "department": "Operations"
    },

    "trade": {
      "symbol": "ACME",
      "trade_date": "2024-03-15",
      "side": "BUY",
      "quantity": 50000,
      "price": "101.50",
      "total_value": "5075000.00"
    },

    "related_event": {
      "event_type": "M&A Announcement",
      "event_date": "2024-03-16",
      "description": "ACME Corp acquired by TechGiant for $150/share"
    }
  },
  "agent_type": "insider_trading",
  "tool_data": {
    "market_news": {"format": "txt", "data": "..."},
    "market_data": {"format": "csv", "data": "..."},
    "trader_profile": {"format": "csv", "data": "..."},
    "trader_history": {"format": "csv", "data": "..."}
  }
}
```

---

## Execution Flow

### Insider Trading Agent - Updated Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INSIDER TRADING - NEW EXECUTION FLOW                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BEFORE (5 tools, alert_reader blocking):                                   │
│  ─────────────────────────────────────────                                  │
│  TOOL_ORDER = [                                                              │
│      "alert_reader",      ← BLOCKING (ran first, others waited)             │
│      "market_news",                                                          │
│      "market_data",                                                          │
│      "trader_profile",                                                       │
│      "trader_history",                                                       │
│  ]                                                                           │
│                                                                              │
│  AFTER (4 tools, all parallel):                                             │
│  ──────────────────────────────                                             │
│  TOOLS = [                  ← No more TOOL_ORDER, all run in parallel       │
│      "market_news",                                                          │
│      "market_data",                                                          │
│      "trader_profile",                                                       │
│      "trader_history",                                                       │
│  ]                                                                           │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Step 1: Read AlertContext (NO tool, NO LLM)                                │
│          ────────────────────────────────────                               │
│          • Direct access: context = request.alert_context                   │
│          • Emit SSE: context_received                                       │
│          • Compute internally:                                              │
│            - start_date = context.trade.trade_date - timedelta(days=30)    │
│            - end_date = context.trade.trade_date + timedelta(days=7)       │
│                     │                                                        │
│                     ▼                                                        │
│  Step 2: Build Context Params                                               │
│          ────────────────────                                               │
│          context_params = {                                                  │
│              "market_news": {                                                │
│                  "symbol": context.trade.symbol,                            │
│                  "start_date": str(start_date),                             │
│                  "end_date": str(end_date),                                 │
│              },                                                              │
│              "market_data": {                                                │
│                  "symbol": context.trade.symbol,                            │
│                  "start_date": str(start_date),                             │
│                  "end_date": str(end_date),                                 │
│              },                                                              │
│              "trader_profile": {                                             │
│                  "trader_id": context.trader.trader_id,                     │
│              },                                                              │
│              "trader_history": {                                             │
│                  "trader_id": context.trader.trader_id,                     │
│                  "symbol": context.trade.symbol,                            │
│                  "trade_date": str(context.trade.trade_date),              │
│              },                                                              │
│          }                                                                   │
│                     │                                                        │
│                     ▼                                                        │
│  Step 3: Execute ALL Tools in Parallel                                      │
│          ─────────────────────────────────                                  │
│          coroutines = [                                                      │
│              tool.aexecute(data=..., format=..., **context_params[name])   │
│              for name, tool in tools.items()                                │
│          ]                                                                   │
│          results = await asyncio.gather(*coroutines)                        │
│                     │                                                        │
│                     ▼                                                        │
│  Step 4: Final Synthesis                                                    │
│          ───────────────                                                    │
│          decision = _synthesize(all_insights)                               │
│          Emit SSE: analysis_complete                                        │
│          Return: InsiderTradingDecision                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Wash Trade Agent - Updated Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WASH TRADE - NEW EXECUTION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  AFTER (5 tools, all parallel):                                             │
│  ──────────────────────────────                                             │
│  TOOLS = [                                                                   │
│      "market_data",                                                          │
│      "account_relationships",                                                │
│      "related_accounts_history",                                             │
│      "trade_timing",                                                         │
│      "counterparty_analysis",                                                │
│  ]                                                                           │
│                                                                              │
│  Same pattern as IT Agent:                                                  │
│  1. Read AlertContext directly                                              │
│  2. Build context params                                                    │
│  3. Execute ALL tools in parallel                                           │
│  4. Final synthesis → WashTradeDecision                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Changes

### 1. Delete AlertReaderTool

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FILE: src/alerts/tools/common/alert_reader.py                              │
│  ACTION: DELETE                                                              │
│                                                                              │
│  This file contains:                                                         │
│  • AlertReaderTool class (~180 lines)                                       │
│  • _build_interpretation_prompt() - LLM prompt for XML parsing             │
│  • parse_alert_context() - regex extraction (MOVE to BigDataSimulator)     │
│                                                                              │
│  MIGRATION:                                                                  │
│  • LLM interpretation: REMOVED (unnecessary)                                │
│  • parse_alert_context() logic: MOVED to BigDataSimulator                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. Update BigDataSimulator

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FILE: src/alerts/mock/bigdata_simulator.py                                  │
│  ACTION: MODIFY                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BEFORE:                                                                     │
│  ───────                                                                     │
│  def create_request(self, alert_file: str) -> AnalysisRequest:             │
│      alert_xml = self._read_file(alert_file)                                │
│      agent_type = self._determine_agent_type(alert_xml)                     │
│      tool_data = self._load_tool_data(agent_type, alert_xml)               │
│                                     ▲                                        │
│                                     │                                        │
│                          Included alert_reader in tool_data                 │
│      return AnalysisRequest(                                                │
│          alert_xml=alert_xml,    ← Raw XML string                           │
│          agent_type=agent_type,                                             │
│          tool_data=tool_data,                                               │
│      )                                                                       │
│                                                                              │
│  AFTER:                                                                      │
│  ──────                                                                      │
│  def create_request(self, alert_file: str) -> AnalysisRequest:             │
│      xml_content = self._read_file(alert_file)                              │
│      alert_context = self._parse_xml_to_context(xml_content)  ← NEW        │
│      agent_type = self._determine_agent_type_from_context(alert_context)   │
│      tool_data = self._load_tool_data(agent_type)  ← No alert_reader       │
│                                                                              │
│      return AnalysisRequest(                                                │
│          alert_context=alert_context,  ← Structured AlertContext            │
│          agent_type=agent_type,                                             │
│          tool_data=tool_data,                                               │
│      )                                                                       │
│                                                                              │
│  NEW METHOD:                                                                 │
│  ───────────                                                                 │
│  def _parse_xml_to_context(self, xml: str) -> AlertContext:                │
│      """Pure regex extraction, NO LLM."""                                   │
│      alert_id = self._extract_tag(xml, "AlertID")                          │
│      alert_type = self._extract_tag(xml, "AlertType")                      │
│      ...                                                                     │
│      return AlertContext(                                                    │
│          alert_id=alert_id,                                                  │
│          alert_type=alert_type,                                             │
│          trader=Trader(...),                                                 │
│          trade=Trade(...),                                                   │
│          related_event=RelatedEvent(...) if present else None,             │
│      )                                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. Update Agents

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FILES:                                                                      │
│  • src/alerts/agents/insider_trading/agent.py                               │
│  • src/alerts/agents/wash_trade/agent.py                                    │
│  ACTION: MODIFY                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CHANGES:                                                                    │
│                                                                              │
│  1. Remove AlertReaderTool from tool instances:                             │
│     - self.alert_reader = AlertReaderTool(...)      ← DELETE               │
│                                                                              │
│  2. Remove TOOL_ORDER with alert_reader first:                              │
│     - TOOL_ORDER = ["read_alert", "query_market_news", ...]  ← DELETE      │
│     + TOOLS = ["query_market_news", "query_market_data", ...]  ← ADD       │
│                                                                              │
│  3. Update analyze_request() method:                                        │
│                                                                              │
│     BEFORE:                                                                  │
│     ───────                                                                  │
│     # Step 1: Execute alert_reader FIRST (blocking)                         │
│     alert_input = request.tool_data.get("alert_reader")                    │
│     alert_insight = self.alert_reader.execute(                             │
│         data=alert_input.data, format=alert_input.format                   │
│     )                                                                        │
│     context = AlertReaderTool.parse_alert_context(alert_input.data)        │
│                                                                              │
│     # Step 2: Build context params from extracted context                   │
│     context_params = self._build_context_params(context)                   │
│                                                                              │
│     # Step 3: Execute remaining tools                                       │
│     for tool_name in self.TOOL_ORDER[1:]:  # Skip alert_reader             │
│         ...                                                                  │
│                                                                              │
│     AFTER:                                                                   │
│     ──────                                                                   │
│     # Step 1: Read context directly (NO tool, NO LLM)                       │
│     context = request.alert_context                                         │
│     self._emit_context_received_event(context)                             │
│                                                                              │
│     # Compute date ranges internally                                        │
│     start_date = context.trade.trade_date - timedelta(days=30)             │
│     end_date = context.trade.trade_date + timedelta(days=7)                │
│                                                                              │
│     # Step 2: Build context params from AlertContext                        │
│     context_params = {                                                       │
│         "query_market_news": {                                               │
│             "symbol": context.trade.symbol,                                  │
│             "start_date": str(start_date),                                  │
│             "end_date": str(end_date),                                      │
│         },                                                                   │
│         ...                                                                  │
│     }                                                                        │
│                                                                              │
│     # Step 3: Execute ALL tools in parallel                                 │
│     coroutines = [                                                           │
│         self._aexecute_single_tool(tool_name, request, context_params)     │
│         for tool_name in self.TOOLS                                         │
│     ]                                                                        │
│     results = await asyncio.gather(*coroutines)                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4. Update tools/common/__init__.py

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FILE: src/alerts/tools/common/__init__.py                                   │
│  ACTION: MODIFY                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BEFORE:                                                                     │
│  ───────                                                                     │
│  from .alert_reader import AlertReaderTool   ← DELETE                       │
│  from .market_data import MarketDataTool                                    │
│  from .trader_profile import TraderProfileTool                              │
│  ...                                                                         │
│                                                                              │
│  __all__ = [                                                                 │
│      "AlertReaderTool",   ← DELETE                                          │
│      "MarketDataTool",                                                       │
│      "TraderProfileTool",                                                   │
│      ...                                                                     │
│  ]                                                                           │
│                                                                              │
│  AFTER:                                                                      │
│  ──────                                                                      │
│  from .market_data import MarketDataTool                                    │
│  from .trader_profile import TraderProfileTool                              │
│  ...                                                                         │
│                                                                              │
│  __all__ = [                                                                 │
│      "MarketDataTool",                                                       │
│      "TraderProfileTool",                                                   │
│      ...                                                                     │
│  ]                                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## SSE Event Changes

### Event Timeline Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BEFORE:                                                                     │
│  ───────                                                                     │
│  analysis_started                                                            │
│       ↓                                                                      │
│  tool_started(alert_reader)     ← AlertReaderTool                           │
│       ↓                                                                      │
│  tool_progress(alert_reader)                                                │
│       ↓                                                                      │
│  tool_completed(alert_reader)                                               │
│       ↓                                                                      │
│  tool_started(market_news)      ← Other tools start AFTER alert_reader     │
│  tool_started(market_data)                                                   │
│  tool_started(trader_profile)                                               │
│  tool_started(trader_history)                                               │
│       ↓                                                                      │
│  tool_completed(...)                                                         │
│       ↓                                                                      │
│  analysis_complete                                                           │
│                                                                              │
│  AFTER:                                                                      │
│  ──────                                                                      │
│  analysis_started                                                            │
│       ↓                                                                      │
│  context_received               ← NEW synthetic event (replaces alert_reader)│
│       ↓                                                                      │
│  tool_started(market_news)      ← ALL tools start immediately              │
│  tool_started(market_data)                                                   │
│  tool_started(trader_profile)                                               │
│  tool_started(trader_history)                                               │
│       ↓                                                                      │
│  tool_completed(...)                                                         │
│       ↓                                                                      │
│  analysis_complete                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### New Event: context_received

**File**: `src/alerts/a2a/event_mapper.py`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ADD NEW EVENT TYPE:                                                         │
│                                                                              │
│  EVENT_TYPES = [                                                             │
│      "analysis_started",                                                     │
│      "context_received",      ← NEW                                         │
│      "tool_started",                                                         │
│      "tool_progress",                                                        │
│      "tool_completed",                                                       │
│      "evaluation_started",                                                   │
│      "analysis_complete",                                                    │
│      "error",                                                                │
│  ]                                                                           │
│                                                                              │
│  ADD NEW METHOD:                                                             │
│                                                                              │
│  def create_context_received_event(                                         │
│      self,                                                                   │
│      alert_id: str,                                                          │
│      trader_id: str,                                                         │
│      symbol: str,                                                            │
│  ) -> StreamEvent:                                                           │
│      """Synthetic event when AlertContext is received."""                   │
│      return self.create_event(                                               │
│          event_type="context_received",                                      │
│          payload={                                                           │
│              "message": f"Alert context received: {alert_id}",              │
│              "alert_id": alert_id,                                           │
│              "trader_id": trader_id,                                         │
│              "symbol": symbol,                                               │
│          },                                                                  │
│      )                                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Frontend Updates

**File**: `src/frontend/static/js/progress-timeline.js`

```javascript
_handleEvent(event) {
    switch (event.event_type) {
        case 'context_received':  // NEW
            this._addTimelineItem({
                icon: '📋',
                title: 'Alert Context Received',
                message: `Alert ${event.payload.alert_id} | ` +
                         `Trader: ${event.payload.trader_id} | ` +
                         `Symbol: ${event.payload.symbol}`,
                status: 'completed',
            });
            break;
        // ... existing cases
    }
}
```

---

## Technology Stack

### No New Dependencies

This change does not require any new libraries or frameworks.

### Existing Stack (Unchanged)

| Dependency | Version | Purpose |
|------------|---------|---------|
| pydantic | >=2.0 | AlertContext, AnalysisRequest models |
| fastapi | >=0.100.0 | HTTP API |
| langchain-core | >=0.3.0 | LLM abstractions (tools still use LLM) |
| sse-starlette | >=1.6.0 | SSE streaming |

### Removed Code (No Dependency Changes)

| Component | Reason |
|-----------|--------|
| AlertReaderTool class | Replaced by AlertContext |
| AlertReaderTool LLM prompt | No longer needed |
| alert_reader in TOOL_ORDER | No longer needed |

---

## Files Changed Summary

| Action | File Path | Description |
|--------|-----------|-------------|
| **CREATE** | `src/alerts/models/alert_context.py` | AlertContext, Trader, Trade, RelatedEvent models |
| **DELETE** | `src/alerts/tools/common/alert_reader.py` | Remove entire file |
| **MODIFY** | `src/alerts/models/request.py` | Replace alert_xml with alert_context, remove alert_reader from REQUIRED_TOOLS |
| **MODIFY** | `src/alerts/models/__init__.py` | Export AlertContext |
| **MODIFY** | `src/alerts/tools/common/__init__.py` | Remove AlertReaderTool export |
| **MODIFY** | `src/alerts/mock/bigdata_simulator.py` | Add _parse_xml_to_context(), create AlertContext |
| **MODIFY** | `src/alerts/agents/insider_trading/agent.py` | Remove alert_reader, read alert_context directly |
| **MODIFY** | `src/alerts/agents/wash_trade/agent.py` | Remove alert_reader, read alert_context directly |
| **MODIFY** | `src/alerts/a2a/event_mapper.py` | Add context_received event type |
| **MODIFY** | `src/alerts/a2a/orchestrator.py` | Update to use alert_context |
| **MODIFY** | `src/frontend/static/js/progress-timeline.js` | Handle context_received event |
| **MODIFY** | `src/frontend/static/js/dag-visualization.js` | Update DAG for new flow |
| **DELETE** | Tests for AlertReaderTool | Remove obsolete tests |
| **CREATE** | Tests for AlertContext | Add new model tests |
| **MODIFY** | Existing integration tests | Update to use alert_context |

---

## Testing Strategy

### Unit Tests

| Test Category | What to Test |
|---------------|--------------|
| AlertContext Validation | Pydantic model validation, required fields, optional related_event |
| Trader Model | trader_id, name, department validation |
| Trade Model | symbol, trade_date, side enum, decimal price/total_value |
| RelatedEvent Model | Optional field handling |
| AnalysisRequest | alert_context required, tool_data without alert_reader |
| BigDataSimulator | XML→AlertContext parsing, all fields extracted correctly |

### Integration Tests

| Test Scenario | Verification |
|---------------|--------------|
| Full IT Analysis | AlertContext → 4 parallel tools → InsiderTradingDecision |
| Full WT Analysis | AlertContext → 5 parallel tools → WashTradeDecision |
| SSE Events | context_received emitted, no alert_reader events |
| Missing tool_data | Returns 400 error (but no alert_reader check) |
| Parallel Execution | Verify all tools start simultaneously (no blocking) |

### Regression Tests

| Test Scenario | Verification |
|---------------|--------------|
| Decision Quality | Same decisions as before (quality unchanged) |
| Report Generation | HTML/JSON reports still generated correctly |
| Frontend Timeline | Timeline displays correctly with context_received |

---

## Design Decisions

### Decision 1: Remove LLM from Alert Parsing

**Context**: AlertReaderTool used LLM to interpret XML.

**Decision**: Remove LLM, use pure regex extraction.

**Rationale**:
- XML has fixed, known structure
- Regex is sufficient for extraction
- LLM adds latency with no benefit
- Other tools already have their own LLM interpretation

### Decision 2: Exclude AnomalyIndicators

**Context**: XML contains `<AnomalyIndicators>` with scores.

**Decision**: Exclude from AlertContext.

**Rationale**:
- AnomalyIndicators is SMARTS pre-analysis, not raw data
- Agent should perform its own analysis
- Avoids biasing agent with pre-computed scores
- Aligns with "pure agentic reasoning" philosophy

### Decision 3: Agent Computes Date Ranges

**Context**: Tools need start_date/end_date for queries.

**Decision**: Agent computes from trade_date (not Big Data Layer).

**Rationale**:
- Date ranges are analysis parameters, not raw data
- Big Data Layer only does XML→JSON transformation
- Agent can adjust ranges based on analysis needs
- Keeps Big Data Layer simple

### Decision 4: Synthetic context_received Event

**Context**: Removing AlertReaderTool changes SSE timeline.

**Decision**: Emit synthetic `context_received` event.

**Rationale**:
- Maintains UI consistency
- Shows users that context was loaded
- Replaces alert_reader events in timeline
- No functional change, just observability

### Decision 5: No Backward Compatibility

**Context**: Should we support both old and new formats?

**Decision**: Clean break, no shims.

**Rationale**:
- Fail-fast philosophy
- Shims add complexity and technical debt
- Clear migration path for Big Data Layer
- Tests will catch any issues immediately

---

## Appendix: Migration Checklist

- [ ] Create `src/alerts/models/alert_context.py`
- [ ] Update `src/alerts/models/request.py` (alert_context, remove alert_reader)
- [ ] Delete `src/alerts/tools/common/alert_reader.py`
- [ ] Update `src/alerts/tools/common/__init__.py`
- [ ] Update `src/alerts/mock/bigdata_simulator.py`
- [ ] Update `src/alerts/agents/insider_trading/agent.py`
- [ ] Update `src/alerts/agents/wash_trade/agent.py`
- [ ] Update `src/alerts/a2a/event_mapper.py`
- [ ] Update `src/alerts/a2a/orchestrator.py`
- [ ] Update `src/frontend/static/js/progress-timeline.js`
- [ ] Update `src/frontend/static/js/dag-visualization.js`
- [ ] Delete AlertReaderTool tests
- [ ] Create AlertContext tests
- [ ] Update integration tests
- [ ] Run full test suite
- [ ] Update CLAUDE.md documentation
