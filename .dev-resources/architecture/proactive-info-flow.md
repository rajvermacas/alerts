# Proactive Information Flow Architecture

**Version:** 1.0
**Status:** Draft
**Last Updated:** 2025-01-07
**Author:** Architecture Team

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Target Architecture](#target-architecture)
4. [Execution Flow](#execution-flow)
5. [API Contract (OpenAPI)](#api-contract-openapi)
6. [Component Design](#component-design)
7. [Tool Data Requirements](#tool-data-requirements)
8. [Technology Stack](#technology-stack)
9. [Migration Strategy](#migration-strategy)
10. [Testing Strategy](#testing-strategy)
11. [Design Decisions](#design-decisions)

---

## Overview

This document describes the architectural changes required to shift from **reactive data loading** (tools load their own data) to **proactive information flow** (data injected from upstream Big Data Layer).

### Key Characteristics

- **External Data Aggregation**: Big Data Layer (external team) aggregates and provides all required data
- **Deterministic Tool Execution**: Fixed tool sequence, no LLM-based routing
- **Fail-Fast**: Missing data causes immediate failure, no fallbacks
- **Contract-Driven**: OpenAPI spec defines integration contract with Big Data Team
- **Unified Pattern**: Same architecture for Insider Trading and Wash Trade agents

---

## Problem Statement

### Current State

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CURRENT ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User/UI ──► Orchestrator ──► InsiderTradingAgent ──► Tools                 │
│                                       │                                      │
│                                       ▼                                      │
│                              ┌─────────────────┐                             │
│                              │ Each tool loads │                             │
│                              │ CSV/TXT from    │                             │
│                              │ test_data/      │                             │
│                              │ internally      │                             │
│                              └─────────────────┘                             │
│                                                                              │
│  PROBLEMS:                                                                   │
│  ─────────                                                                   │
│  1. Tools coupled to file system (not scalable)                             │
│  2. LLM decides tool order (non-deterministic, unpredictable)               │
│  3. No separation between data aggregation and analysis                     │
│  4. Cannot handle production-scale trade data                               │
│  5. Orchestrator/Agent responsible for data loading (wrong layer)           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Target State

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TARGET ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Big Data Layer ──► Orchestrator ──► Agent ──► Tools (data injected)        │
│       │                  │              │           │                        │
│       │                  │              │           │                        │
│       ▼                  ▼              ▼           ▼                        │
│  Aggregates data    Thin router    Deterministic  Receive data              │
│  from production    (no loading)   tool loop      via kwargs                │
│  systems                           (no LLM                                   │
│                                    routing)                                  │
│                                                                              │
│  BENEFITS:                                                                   │
│  ─────────                                                                   │
│  1. Tools decoupled from data source (any data source works)                │
│  2. Predictable, reproducible tool execution order                          │
│  3. Big Data Layer handles scale (Spark, Hadoop, etc.)                      │
│  4. Clear contract between teams                                            │
│  5. Easier testing with mock data                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FULL SYSTEM ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │              BIG DATA LAYER (External Team)                         │     │
│  │              ───────────────────────────────                        │     │
│  │                                                                     │     │
│  │  Responsibilities:                                                  │     │
│  │  • Ingest raw alerts from SMARTS surveillance system               │     │
│  │  • Query production databases for trader/market data               │     │
│  │  • Filter and aggregate relevant data per tool requirements        │     │
│  │  • Determine agent_type (insider_trading | wash_trade)             │     │
│  │  • Construct AnalysisRequest JSON payload                          │     │
│  │                                                                     │     │
│  │  Technology: Spark, Hadoop, etc. (their choice)                    │     │
│  │                                                                     │     │
│  └───────────────────────────┬────────────────────────────────────────┘     │
│                              │                                               │
│                              │ HTTP POST /api/analyze                        │
│                              │ Content-Type: application/json                │
│                              │ Body: AnalysisRequest                         │
│                              ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │              ORCHESTRATOR (Port 10000)                              │     │
│  │              ─────────────────────────                              │     │
│  │                                                                     │     │
│  │  Responsibilities:                                                  │     │
│  │  • Validate AnalysisRequest schema (Pydantic)                      │     │
│  │  • Route to correct agent based on agent_type                      │     │
│  │  • Pass tool_data bundle unchanged                                 │     │
│  │  • Emit SSE events for progress tracking                           │     │
│  │                                                                     │     │
│  │  NO data loading, NO LLM calls, NO business logic                  │     │
│  │                                                                     │     │
│  └───────────────────────────┬────────────────────────────────────────┘     │
│                              │                                               │
│                              │ A2A JSON-RPC                                  │
│                              │ (extended payload with tool_data)             │
│                              ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │              ANALYSIS AGENT (IT: 10001, WT: 10002)                  │     │
│  │              ─────────────────────────────────────                  │     │
│  │                                                                     │     │
│  │  ┌──────────────────────────────────────────────────────────────┐  │     │
│  │  │  DETERMINISTIC TOOL EXECUTOR (Plain Python Loop)             │  │     │
│  │  │                                                               │  │     │
│  │  │  for tool_name in HARDCODED_TOOL_ORDER:                      │  │     │
│  │  │      data = tool_data[tool_name]                             │  │     │
│  │  │      if data is None: raise MissingToolDataError             │  │     │
│  │  │      emit_sse("tool_started", tool_name)                     │  │     │
│  │  │      insight = tool.execute(data=data)  # LLM inside         │  │     │
│  │  │      emit_sse("tool_completed", tool_name)                   │  │     │
│  │  │      insights[tool_name] = insight                           │  │     │
│  │  │                                                               │  │     │
│  │  └──────────────────────────────────────────────────────────────┘  │     │
│  │                              │                                      │     │
│  │                              ▼                                      │     │
│  │  ┌──────────────────────────────────────────────────────────────┐  │     │
│  │  │  FINAL SYNTHESIS (Single LLM Call)                           │  │     │
│  │  │                                                               │  │     │
│  │  │  Input: system_prompt + few_shot_examples + all_insights     │  │     │
│  │  │  Output: InsiderTradingDecision / WashTradeDecision          │  │     │
│  │  │                                                               │  │     │
│  │  │  This is the ONLY agentic reasoning step                     │  │     │
│  │  └──────────────────────────────────────────────────────────────┘  │     │
│  │                                                                     │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Execution Flow

### Insider Trading Agent - Tool Execution Order

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INSIDER TRADING - FIXED EXECUTION ORDER                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TOOL_ORDER = [                                                              │
│      "alert_reader",                                                         │
│      "market_news",                                                          │
│      "market_data",                                                          │
│      "trader_profile",                                                       │
│      "trader_history",                                                       │
│  ]                                                                           │
│                                                                              │
│  NOTE: peer_trades REMOVED from execution order                              │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Step 1: alert_reader                                                        │
│          ─────────────                                                       │
│          Input:  tool_data["alert_reader"] (XML content)                     │
│          LLM:    Parses alert XML, extracts key fields                       │
│          Output: AlertSummary (trader_id, symbol, quantity, timing, rule)    │
│                     │                                                        │
│                     ▼                                                        │
│  Step 2: market_news                                                         │
│          ───────────                                                         │
│          Input:  tool_data["market_news"] (TXT content)                      │
│          LLM:    Analyzes news timeline relative to trade date               │
│          Output: NewsAnalysis (material events, public info timeline)        │
│                     │                                                        │
│                     ▼                                                        │
│  Step 3: market_data                                                         │
│          ───────────                                                         │
│          Input:  tool_data["market_data"] (CSV content)                      │
│          LLM:    Assesses market conditions, volatility                      │
│          Output: MarketContext (price movements, volume patterns)            │
│                     │                                                        │
│                     ▼                                                        │
│  Step 4: trader_profile                                                      │
│          ──────────────                                                      │
│          Input:  tool_data["trader_profile"] (CSV content)                   │
│          LLM:    Evaluates MNPI access, role, department                     │
│          Output: TraderRiskAssessment (access level, risk factors)           │
│                     │                                                        │
│                     ▼                                                        │
│  Step 5: trader_history                                                      │
│          ──────────────                                                      │
│          Input:  tool_data["trader_history"] (CSV content)                   │
│          LLM:    Compares flagged trade against historical baseline          │
│          Output: BaselineDeviation (pattern analysis, anomalies)             │
│                     │                                                        │
│                     ▼                                                        │
│  Step 6: FINAL SYNTHESIS                                                     │
│          ───────────────                                                     │
│          Input:  All 5 tool insights + system prompt + few-shot examples     │
│          LLM:    Reasons over all evidence, compares to precedents           │
│          Output: InsiderTradingDecision (determination, confidence, etc.)    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Wash Trade Agent - Tool Execution Order

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WASH TRADE - FIXED EXECUTION ORDER                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TOOL_ORDER = [                                                              │
│      "alert_reader",                                                         │
│      "market_data",                                                          │
│      "account_relationships",                                                │
│      "related_accounts_history",                                             │
│      "trade_timing",                                                         │
│      "counterparty_analysis",                                                │
│  ]                                                                           │
│                                                                              │
│  NOTE: trader_profile NOT included for wash trade (by design decision)       │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Step 1: alert_reader           → AlertSummary                               │
│  Step 2: market_data            → MarketContext                              │
│  Step 3: account_relationships  → OwnershipNetwork                           │
│  Step 4: related_accounts_history → CoordinatedActivityAnalysis              │
│  Step 5: trade_timing           → SubSecondPatterns                          │
│  Step 6: counterparty_analysis  → BeneficialOwnershipOverlap                 │
│  Step 7: FINAL SYNTHESIS        → WashTradeDecision                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Contract (OpenAPI)

This is the contract to be shared with the Big Data Layer team.

### OpenAPI Specification (v3.0)

```yaml
openapi: 3.0.3
info:
  title: SMARTS Alert Analyzer API
  description: |
    API for analyzing SMARTS surveillance alerts for potential insider trading
    or wash trading violations. The Big Data Layer must aggregate all required
    tool data before calling this API.
  version: 1.0.0
  contact:
    name: Alert Analyzer Team

servers:
  - url: http://localhost:10000
    description: Orchestrator (Development)

paths:
  /api/analyze:
    post:
      summary: Analyze a SMARTS alert
      description: |
        Accepts an alert with pre-aggregated tool data and returns an analysis
        decision. The Big Data Layer is responsible for:
        1. Determining the agent_type from alert content
        2. Aggregating all required data for each tool
        3. Providing data in the correct format (csv, txt, xml)
      operationId: analyzeAlert
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AnalysisRequest'
            examples:
              insiderTrading:
                summary: Insider Trading Alert
                value:
                  alert_xml: "<ALERT><RULE_ID>SMARTS-IT-001</RULE_ID>...</ALERT>"
                  agent_type: "insider_trading"
                  tool_data:
                    alert_reader:
                      format: "xml"
                      data: "<ALERT>...</ALERT>"
                    market_news:
                      format: "txt"
                      data: "2024-01-15: Company announces Q4 earnings..."
                    market_data:
                      format: "csv"
                      data: "timestamp,symbol,price,volume\n2024-01-15,AAPL,185.50,1000000"
                    trader_profile:
                      format: "csv"
                      data: "trader_id,name,role,department,mnpi_access\nT123,John Doe,Analyst,Research,HIGH"
                    trader_history:
                      format: "csv"
                      data: "date,symbol,action,quantity,price\n2024-01-10,AAPL,BUY,100,180.00"
      responses:
        '200':
          description: Analysis completed successfully
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: '#/components/schemas/InsiderTradingDecision'
                  - $ref: '#/components/schemas/WashTradeDecision'
        '400':
          description: Invalid request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
              examples:
                missingToolData:
                  value:
                    error: "MISSING_TOOL_DATA"
                    tool: "trader_profile"
                    message: "Required tool data not provided"
                invalidFormat:
                  value:
                    error: "INVALID_FORMAT"
                    tool: "market_data"
                    expected: "csv"
                    received: "json"
                unknownAgent:
                  value:
                    error: "UNKNOWN_AGENT_TYPE"
                    agent_type: "unknown_type"
        '500':
          description: Analysis failed
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

  /api/analyze/stream:
    post:
      summary: Analyze alert with SSE progress streaming
      description: |
        Same as /api/analyze but returns Server-Sent Events for real-time
        progress tracking. Events include tool_started, tool_completed,
        and analysis_complete.
      operationId: analyzeAlertStream
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AnalysisRequest'
      responses:
        '200':
          description: SSE stream of analysis progress
          content:
            text/event-stream:
              schema:
                type: string
                description: Server-Sent Events stream

components:
  schemas:
    AnalysisRequest:
      type: object
      required:
        - alert_xml
        - agent_type
        - tool_data
      properties:
        alert_xml:
          type: string
          description: Full XML content of the SMARTS alert
          example: "<ALERT><RULE_ID>SMARTS-IT-001</RULE_ID>...</ALERT>"
        agent_type:
          type: string
          enum:
            - insider_trading
            - wash_trade
          description: Type of analysis to perform (determined by Big Data Layer)
        tool_data:
          type: object
          description: Pre-aggregated data for each tool
          additionalProperties:
            $ref: '#/components/schemas/ToolInput'

    ToolInput:
      type: object
      required:
        - format
        - data
      properties:
        format:
          type: string
          enum:
            - xml
            - csv
            - txt
          description: Format of the data content
        data:
          type: string
          description: Raw data content (XML string, CSV string, or plain text)

    InsiderTradingDecision:
      type: object
      required:
        - determination
        - genuine_alert_confidence
        - false_positive_confidence
        - reasoning_narrative
      properties:
        determination:
          type: string
          enum:
            - ESCALATE
            - CLOSE
            - NEEDS_HUMAN_REVIEW
        genuine_alert_confidence:
          type: number
          minimum: 0
          maximum: 1
        false_positive_confidence:
          type: number
          minimum: 0
          maximum: 1
        key_findings:
          type: array
          items:
            type: string
        favorable_indicators:
          type: array
          items:
            type: string
        risk_mitigating_factors:
          type: array
          items:
            type: string
        trader_baseline_analysis:
          type: string
        market_context:
          type: string
        reasoning_narrative:
          type: string
        similar_precedent:
          type: string
        recommended_action:
          type: string

    WashTradeDecision:
      type: object
      description: Similar to InsiderTradingDecision with additional wash trade fields
      properties:
        determination:
          type: string
          enum:
            - ESCALATE
            - CLOSE
            - NEEDS_HUMAN_REVIEW
        relationship_network:
          type: object
        timing_patterns:
          type: string
        trade_flows:
          type: string
        counterparty_patterns:
          type: string

    ErrorResponse:
      type: object
      required:
        - error
      properties:
        error:
          type: string
          enum:
            - MISSING_TOOL_DATA
            - INVALID_FORMAT
            - UNKNOWN_AGENT_TYPE
            - ANALYSIS_FAILED
        tool:
          type: string
          description: Tool name (for tool-specific errors)
        expected:
          type: string
          description: Expected value
        received:
          type: string
          description: Received value
        message:
          type: string
          description: Human-readable error message
        details:
          type: string
          description: Additional error details
```

### Tool Data Requirements by Agent Type

| Agent Type | Required Tools | Format |
|------------|----------------|--------|
| `insider_trading` | `alert_reader` | xml |
| | `market_news` | txt |
| | `market_data` | csv |
| | `trader_profile` | csv |
| | `trader_history` | csv |
| `wash_trade` | `alert_reader` | xml |
| | `market_data` | csv |
| | `account_relationships` | csv |
| | `related_accounts_history` | csv |
| | `trade_timing` | csv |
| | `counterparty_analysis` | csv |

**Notes**:
- `peer_trades` has been removed from requirements (deleted entirely).
- `trader_profile` is NOT included in `wash_trade` requirements (design decision - wash trade analysis focuses on account relationships, not individual trader profiles).

---

## Component Design

### 1. Request/Response Models (Pydantic)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PYDANTIC MODELS                                           │
│                    Location: src/alerts/models/request.py                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  class ToolInput(BaseModel):                                                 │
│      format: Literal["xml", "csv", "txt"]                                   │
│      data: str                                                               │
│                                                                              │
│  class AnalysisRequest(BaseModel):                                          │
│      alert_xml: str                                                          │
│      agent_type: Literal["insider_trading", "wash_trade"]                   │
│      tool_data: Dict[str, ToolInput]                                        │
│                                                                              │
│      @model_validator                                                        │
│      def validate_required_tools(self):                                      │
│          # Validate all required tools present for agent_type               │
│          # Raise ValidationError if missing                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. Orchestrator Changes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR MODIFICATIONS                                │
│                    Location: src/alerts/a2a/orchestrator.py                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BEFORE (Current):                                                           │
│  ─────────────────                                                           │
│  - Receives: alert_xml only                                                  │
│  - Does: determine_alert_type(alert_xml)                                    │
│  - Passes: alert_xml to agent                                               │
│                                                                              │
│  AFTER (Target):                                                             │
│  ────────────────                                                            │
│  - Receives: AnalysisRequest (alert_xml + agent_type + tool_data)           │
│  - Does: validate request, route based on agent_type (pre-determined)       │
│  - Passes: entire AnalysisRequest to agent                                  │
│                                                                              │
│  REMOVED:                                                                    │
│  ────────                                                                    │
│  - determine_alert_type() logic (Big Data Layer decides)                    │
│  - Any data loading responsibility                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. Agent Changes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AGENT MODIFICATIONS                                       │
│                    Location: src/alerts/agents/{type}/agent.py               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BEFORE (Current):                                                           │
│  ─────────────────                                                           │
│  - LangGraph agent with dynamic tool routing                                │
│  - LLM decides which tools to call and in what order                        │
│  - Tools load their own data internally                                     │
│                                                                              │
│  AFTER (Target):                                                             │
│  ────────────────                                                            │
│  - Plain Python class with deterministic execution                          │
│  - Hardcoded TOOL_ORDER list                                                │
│  - for-loop iterates through tools in fixed sequence                        │
│  - Each tool receives data from tool_data parameter                         │
│  - Single LLM call at end for final synthesis                               │
│                                                                              │
│  PSEUDO-ALGORITHM:                                                           │
│  ─────────────────                                                           │
│  class InsiderTradingAgent:                                                  │
│      TOOL_ORDER = ["alert_reader", "market_news", "market_data",            │
│                    "trader_profile", "trader_history"]                       │
│                                                                              │
│      def analyze(self, request: AnalysisRequest) -> InsiderTradingDecision:│
│          insights = {}                                                       │
│                                                                              │
│          for tool_name in self.TOOL_ORDER:                                  │
│              tool_input = request.tool_data.get(tool_name)                  │
│              if tool_input is None:                                          │
│                  raise MissingToolDataError(tool_name)                      │
│                                                                              │
│              self.emit_event("tool_started", tool_name)                     │
│              tool = self.tools[tool_name]                                   │
│              insight = tool.execute(data=tool_input.data,                   │
│                                     format=tool_input.format)               │
│              insights[tool_name] = insight                                  │
│              self.emit_event("tool_completed", tool_name)                   │
│                                                                              │
│          # Final synthesis - ONLY LLM reasoning step                        │
│          decision = self._synthesize(insights)                              │
│          return decision                                                     │
│                                                                              │
│      def _synthesize(self, insights: Dict) -> InsiderTradingDecision:      │
│          llm = create_llm()                                                  │
│          prompt = self._build_synthesis_prompt(insights)                    │
│          return llm.with_structured_output(                                  │
│              InsiderTradingDecision                                          │
│          ).invoke(prompt)                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4. Tool Changes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOOL MODIFICATIONS                                        │
│                    Location: src/alerts/tools/common/*.py                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  BEFORE (Current):                                                           │
│  ─────────────────                                                           │
│  class TraderProfileTool(BaseTool):                                         │
│      def _load_data(self, **kwargs) -> str:                                 │
│          # Reads from test_data/trader_profiles.csv                         │
│          with open("test_data/trader_profiles.csv") as f:                   │
│              return f.read()                                                 │
│                                                                              │
│  AFTER (Target):                                                             │
│  ────────────────                                                            │
│  class TraderProfileTool(BaseTool):                                         │
│      def execute(self, data: str, format: str, **kwargs) -> str:           │
│          # Data is INJECTED, not loaded                                     │
│          if data is None:                                                    │
│              raise MissingDataError("trader_profile data not provided")     │
│          if format != "csv":                                                 │
│              raise InvalidFormatError(f"Expected csv, got {format}")        │
│                                                                              │
│          # LLM interpretation remains unchanged                             │
│          prompt = self._build_interpretation_prompt(data, **kwargs)         │
│          return self._interpret_with_llm(prompt)                            │
│                                                                              │
│  KEY CHANGE:                                                                 │
│  ───────────                                                                 │
│  - _load_data() method REMOVED entirely                                     │
│  - Data comes via execute() parameter                                       │
│  - Format validation added                                                   │
│  - Fail-fast if data missing (no fallback to file system)                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5. Mock Big Data Layer (POC Testing)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MOCK BIG DATA LAYER                                       │
│                    Location: src/alerts/mock/bigdata_simulator.py            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Purpose: Simulate Big Data Layer for POC testing and contract validation   │
│                                                                              │
│  class BigDataSimulator:                                                     │
│      """                                                                     │
│      Reads from test_data/ and constructs AnalysisRequest                   │
│      exactly as Big Data Layer would.                                       │
│      """                                                                     │
│                                                                              │
│      def create_request(self, alert_file: str) -> AnalysisRequest:         │
│          alert_xml = self._read_file(alert_file)                            │
│          agent_type = self._determine_agent_type(alert_xml)                 │
│          tool_data = self._load_tool_data(agent_type)                       │
│                                                                              │
│          return AnalysisRequest(                                             │
│              alert_xml=alert_xml,                                            │
│              agent_type=agent_type,                                          │
│              tool_data=tool_data                                             │
│          )                                                                   │
│                                                                              │
│      def _load_tool_data(self, agent_type: str) -> Dict[str, ToolInput]:   │
│          if agent_type == "insider_trading":                                │
│              return {                                                        │
│                  "alert_reader": ToolInput(                                  │
│                      format="xml",                                           │
│                      data=self._read_file("test_data/alerts/alert.xml")     │
│                  ),                                                          │
│                  "market_news": ToolInput(                                   │
│                      format="txt",                                           │
│                      data=self._read_file("test_data/market_news.txt")      │
│                  ),                                                          │
│                  "market_data": ToolInput(                                   │
│                      format="csv",                                           │
│                      data=self._read_file("test_data/market_data.csv")      │
│                  ),                                                          │
│                  "trader_profile": ToolInput(                                │
│                      format="csv",                                           │
│                      data=self._read_file("test_data/trader_profiles.csv") │
│                  ),                                                          │
│                  "trader_history": ToolInput(                                │
│                      format="csv",                                           │
│                      data=self._read_file("test_data/trader_history.csv")  │
│                  ),                                                          │
│              }                                                               │
│          elif agent_type == "wash_trade":                                   │
│              return { ... }  # Similar structure                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tool Data Requirements

### CSV Schema Definitions

These schemas must be communicated to the Big Data Team.

#### trader_profile.csv

```csv
trader_id,name,role,department,mnpi_access,employment_start,compliance_training_date
T123,John Doe,Senior Analyst,Research,HIGH,2020-01-15,2024-06-01
```

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| trader_id | string | Yes | Unique identifier |
| name | string | Yes | Full name |
| role | string | Yes | Job title |
| department | string | Yes | Department name |
| mnpi_access | enum | Yes | HIGH, MEDIUM, LOW, NONE |
| employment_start | date | No | YYYY-MM-DD |
| compliance_training_date | date | No | YYYY-MM-DD |

#### market_data.csv

```csv
timestamp,symbol,price,volume,bid,ask,vwap
2024-01-15T09:30:00,AAPL,185.50,1000000,185.45,185.55,185.48
```

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| timestamp | datetime | Yes | ISO 8601 format |
| symbol | string | Yes | Stock ticker |
| price | decimal | Yes | Trade price |
| volume | integer | Yes | Trade volume |
| bid | decimal | No | Best bid |
| ask | decimal | No | Best ask |
| vwap | decimal | No | Volume-weighted avg price |

#### trader_history.csv

```csv
date,symbol,action,quantity,price,order_type,execution_venue
2024-01-10,AAPL,BUY,100,180.00,LIMIT,NYSE
```

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| date | date | Yes | YYYY-MM-DD |
| symbol | string | Yes | Stock ticker |
| action | enum | Yes | BUY, SELL |
| quantity | integer | Yes | Number of shares |
| price | decimal | Yes | Execution price |
| order_type | enum | No | MARKET, LIMIT |
| execution_venue | string | No | Exchange name |

#### market_news.txt

```
2024-01-15: Company X announces Q4 earnings beat, stock up 5%
2024-01-14: FDA approves new drug from Company Y
2024-01-13: Market closes flat amid economic uncertainty
```

Format: One news item per line, prefixed with date (YYYY-MM-DD).

---

## Technology Stack

### Removed Dependencies

| Dependency | Reason for Removal |
|------------|-------------------|
| LangGraph | No longer needed for deterministic execution |
| langgraph-checkpoint | State persistence not required |

### Retained Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| langchain-core | >=0.3.0 | LLM abstractions, structured output |
| langchain-openai | >=0.2.0 | OpenAI provider |
| langchain-google-genai | >=2.0.0 | Gemini provider |
| pydantic | >=2.0 | Request/response validation |
| fastapi | >=0.100.0 | HTTP API, OpenAPI auto-generation |
| uvicorn | >=0.23.0 | ASGI server |
| httpx | >=0.25.0 | A2A client |
| sse-starlette | >=1.6.0 | SSE streaming |

### New Components (No New Libraries)

| Component | Implementation |
|-----------|---------------|
| AnalysisRequest model | Pydantic BaseModel |
| Deterministic executor | Plain Python for-loop |
| Mock Big Data Layer | Python class reading test_data/ |
| OpenAPI spec | Auto-generated by FastAPI |

---

## Migration Strategy

### Phase 1: Contract Definition
1. Finalize OpenAPI spec
2. Define all CSV schemas
3. Share with Big Data Team
4. Create mock simulator

### Phase 2: Tool Refactoring
1. Modify BaseTool to accept data parameter
2. Remove _load_data() from all tools
3. Add format validation
4. Update tests to inject data

### Phase 3: Agent Refactoring
1. Remove LangGraph dependency
2. Implement deterministic tool executor
3. Hardcode TOOL_ORDER in each agent
4. Keep final synthesis with LLM

### Phase 4: Orchestrator Refactoring
1. Accept AnalysisRequest schema
2. Remove determine_alert_type() (pre-determined)
3. Pass tool_data to agents unchanged

### Phase 5: Integration Testing
1. End-to-end tests with mock Big Data Layer
2. Validate SSE events still emitted
3. Validate all tool insights generated
4. Validate final decision quality

---

## Testing Strategy

### Unit Tests

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Test Category          │ What to Test                                      │
├─────────────────────────┼───────────────────────────────────────────────────┤
│  Request Validation     │ AnalysisRequest Pydantic validation               │
│                         │ - Missing required fields → ValidationError       │
│                         │ - Invalid agent_type → ValidationError            │
│                         │ - Missing tool_data keys → ValidationError        │
├─────────────────────────┼───────────────────────────────────────────────────┤
│  Tool Execution         │ Each tool with injected data                      │
│                         │ - Valid data → returns insight string             │
│                         │ - None data → raises MissingDataError             │
│                         │ - Wrong format → raises InvalidFormatError        │
├─────────────────────────┼───────────────────────────────────────────────────┤
│  Agent Execution        │ Deterministic flow                                │
│                         │ - All tools called in TOOL_ORDER sequence         │
│                         │ - SSE events emitted for each tool                │
│                         │ - Final synthesis produces valid decision         │
├─────────────────────────┼───────────────────────────────────────────────────┤
│  Mock Big Data Layer    │ Request construction                              │
│                         │ - Reads test_data files correctly                 │
│                         │ - Produces valid AnalysisRequest                  │
└─────────────────────────┴───────────────────────────────────────────────────┘
```

### Integration Tests

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Test Scenario                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. Mock Big Data → Orchestrator → IT Agent → Decision                      │
│     Verify: Full flow produces InsiderTradingDecision                       │
│                                                                              │
│  2. Mock Big Data → Orchestrator → WT Agent → Decision                      │
│     Verify: Full flow produces WashTradeDecision                            │
│                                                                              │
│  3. SSE Streaming                                                            │
│     Verify: tool_started, tool_completed events for each tool               │
│                                                                              │
│  4. Error Handling                                                           │
│     Verify: Missing tool_data returns 400 with correct error schema         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Design Decisions

### Decision 1: Drop LangGraph

**Context**: Current implementation uses LangGraph for dynamic tool routing.

**Decision**: Remove LangGraph, use plain Python for-loop.

**Rationale**:
- Tool execution order is now deterministic (business requirement)
- LangGraph's value is dynamic routing, which is no longer needed
- Simpler debugging and predictable behavior
- One less dependency to maintain

**Trade-offs**:
- (+) Simpler, more predictable
- (+) Easier to test
- (-) Manual SSE event emission required
- (-) Lose LangGraph's built-in state management (not needed for this flow)

### Decision 2: Data Injection via Parameters

**Context**: How should tools receive data?

**Decision**: Data injected via execute() method parameters.

**Rationale**:
- Explicit contract (parameter must be provided)
- Fail-fast if missing
- Tools remain stateless
- Easy to test with any data

**Alternative Considered**: Shared context object
- Rejected: Adds implicit coupling, harder to trace data flow

### Decision 3: Hardcoded Tool Order

**Context**: Where to define tool execution sequence?

**Decision**: Hardcode TOOL_ORDER list in each agent class.

**Rationale**:
- Explicit, type-safe, no config parsing errors
- Easy to understand and modify
- Fails at development time if tool missing
- Different agents can have different orders

**Alternative Considered**: Configuration file
- Rejected: Runtime errors harder to debug, adds indirection

### Decision 4: Fail-Fast, No Fallbacks

**Context**: What if tool data is missing?

**Decision**: Raise exception immediately, no fallback to file loading.

**Rationale**:
- Matches project philosophy (fail-fast)
- Forces Big Data Layer to provide complete data
- No silent degradation that hides bugs
- Clear error messages for debugging

### Decision 5: OpenAPI for Contract

**Context**: What format for cross-team API contract?

**Decision**: OpenAPI 3.0 specification.

**Rationale**:
- Industry standard for REST APIs
- Auto-generated by FastAPI from Pydantic models
- Enables client SDK generation
- Provides interactive documentation (Swagger UI)
- Includes JSON Schema for payload validation

---

## Appendix: SSE Events

Events emitted during analysis (unchanged from current behavior):

| Event | Payload | When |
|-------|---------|------|
| `analysis_started` | `{agent_type, alert_id}` | Analysis begins |
| `tool_started` | `{tool_name}` | Before each tool executes |
| `tool_completed` | `{tool_name, duration_ms}` | After each tool completes |
| `synthesis_started` | `{}` | Before final LLM reasoning |
| `analysis_complete` | `{determination}` | Analysis finished |
| `error` | `{error_type, message}` | On any failure |

---

## Appendix: File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/alerts/models/request.py` | CREATE | AnalysisRequest, ToolInput models |
| `src/alerts/mock/bigdata_simulator.py` | CREATE | Mock Big Data Layer |
| `src/alerts/a2a/orchestrator.py` | MODIFY | Accept AnalysisRequest |
| `src/alerts/agents/insider_trading/agent.py` | MODIFY | Deterministic executor |
| `src/alerts/agents/wash_trade/agent.py` | MODIFY | Deterministic executor |
| `src/alerts/tools/common/base.py` | MODIFY | Accept data parameter |
| `src/alerts/tools/common/*.py` | MODIFY | Remove _load_data() |
| `src/alerts/agents/*/tools/*.py` | MODIFY | Remove _load_data() |
| `tests/test_request_models.py` | CREATE | Request validation tests |
| `tests/test_deterministic_agent.py` | CREATE | Agent execution tests |
| `pyproject.toml` | MODIFY | Remove langgraph dependency |
