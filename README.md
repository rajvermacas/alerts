# SMARTS Alert False Positive Analyzer

An intelligent compliance filter that analyzes SMARTS surveillance alerts to reduce false positive rates before escalating to human compliance analysts. The system uses a fully agentic LLM-based approach with no hardcoded scoring weights.

## Overview

This system supports multiple alert types through a multi-agent architecture:
- **Insider Trading Alerts**: Analyzes pre-announcement trading, MNPI-based trades
- **Wash Trade Alerts**: Detects same beneficial ownership, pre-arranged execution, circular trade flows

The POC system automates the initial analysis of surveillance alerts by:
- Reading SMARTS alert XML files
- Gathering evidence from multiple data sources (trader history, profiles, market data, news, peer activity)
- Using LLM interpretation at each tool to extract insights (not raw data)
- Applying "case law" reasoning by comparing to few-shot precedent examples
- Producing structured decisions with detailed reasoning

## Features

- **Fully Agentic**: Pure LLM reasoning without deterministic scoring
- **Multi-Agent Architecture**: Specialized agents for different alert types (insider trading, wash trade)
- **A2A Protocol**: Google's Agent-to-Agent protocol for inter-agent communication
- **10 Specialized Tools**: 6 shared tools + 4 wash-trade-specific tools, each calling LLM internally
- **Few-Shot Learning**: Examples stored in external JSON for easy tuning
- **Structured Output**: Pydantic models ensure consistent, parseable decisions
- **Relationship Network Visualization**: SVG network graphs for wash trade analysis
- **Audit Trail**: All decisions logged for compliance tracking
- **Fail-Fast**: No graceful degradation; errors crash loudly for debugging
- **APAC Regulatory Framework**: Supports MAS SFA, SFC SFO, ASIC, FSA FIEA compliance

## Decision Outcomes

| Determination | Condition | Action |
|---------------|-----------|--------|
| `ESCALATE` | High confidence of genuine violation (insider trading or wash trade) | Route to compliance analyst |
| `CLOSE` | High confidence of false positive | Auto-close with documentation |
| `NEEDS_HUMAN_REVIEW` | Conflicting signals, cannot decide | Route for human judgment |

## Installation

### Prerequisites

- Python 3.10+
- OpenAI API key (or Azure OpenAI)

### Setup

```bash
# Clone the repository
cd alerts

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# For development
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API key
```

## Configuration

Edit `.env` file:

```bash
# LLM Provider: "openai" or "azure"
LLM_PROVIDER=openai

# OpenAI Configuration
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Azure OpenAI Configuration (if using Azure)
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Paths
DATA_DIR=test_data
OUTPUT_DIR=resources/reports

# Logging
LOG_LEVEL=INFO
```

## Usage

### Analyze an Alert

```bash
# Analyze the default genuine insider trading case
python -m alerts.main

# Analyze a specific alert file
python -m alerts.main --alert test_data/alerts/alert_genuine.xml

# Run with verbose logging
python -m alerts.main --verbose

# Analyze the false positive test case
python -m alerts.main --alert test_data/alerts/alert_false_positive.xml

# Analyze the ambiguous case
python -m alerts.main --alert test_data/alerts/alert_ambiguous.xml
```

### Output

The analyzer produces:
1. **Decision file**: `resources/reports/decision_{alert_id}.json`
2. **Audit log**: `resources/reports/audit_log.jsonl` (appended)

## Multi-Agent Orchestration (A2A Protocol)

The system supports multi-agent orchestration using Google's Agent-to-Agent (A2A) protocol. An orchestrator agent routes alerts to specialized agents based on alert type.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 Orchestrator Agent (Port 10000)                 │
│  Reads alerts, determines type, routes to specialized agents    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ A2A Protocol (JSON-RPC over HTTP)
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
┌───────────────────────────┐   ┌───────────────────────────────┐
│   Insider Trading Agent   │   │     Wash Trade Agent          │
│      (Port 10001)         │   │       (Port 10002)            │
└───────────────────────────┘   └───────────────────────────────┘
```

### Running Multi-Agent Setup

**Terminal 1** - Start the Insider Trading Agent server:
```bash
python -m alerts.a2a.insider_trading_server --port 10001

# Or using the console script:
alerts-insider-trading-server --port 10001
```

**Terminal 2** - Start the Wash Trade Agent server:
```bash
python -m alerts.a2a.wash_trade_server --port 10002

# Or using the console script:
alerts-wash-trade-server --port 10002
```

**Terminal 3** - Start the Orchestrator server:
```bash
python -m alerts.a2a.orchestrator_server --port 10000

# Or using the console script:
alerts-orchestrator-server --port 10000 \
    --insider-trading-url http://localhost:10001 \
    --wash-trade-url http://localhost:10002
```

**Terminal 4** - Test with the client:
```bash
# Test insider trading alert
python -m alerts.a2a.test_client \
    --server-url http://localhost:10000 \
    --alert test_data/alerts/alert_genuine.xml

# Test wash trade alert
python -m alerts.a2a.test_client \
    --server-url http://localhost:10000 \
    --alert test_data/alerts/wash_trade/wash_genuine.xml
```

### Agent Communication

The orchestrator reads alert XML files and determines alert type by checking:

**Insider Trading Detection:**
- Alert type (e.g., "Pre-Announcement Trading", "Insider Trading")
- Rule code (e.g., "SMARTS-IT-001", "SMARTS-PAT-001")
- Keywords (e.g., "insider", "pre-announcement", "mnpi", "material")

**Wash Trade Detection:**
- Alert type (e.g., "WashTrade", "Self-Trade", "Matched Orders", "Circular Trading")
- Rule code (e.g., "SMARTS-WT-001", "WT-001", "WASH_TRADE", "SELF_TRADE")
- Keywords (e.g., "wash", "self-trade", "matched order", "circular")

### Configuration

Server URLs can be configured via command-line options:
```bash
alerts-orchestrator-server --port 10000 \
    --insider-trading-url http://remote-host:10001 \
    --wash-trade-url http://remote-host:10002
```

For production deployments, consider setting environment variables:
```bash
# .env configuration (future enhancement)
INSIDER_TRADING_AGENT_URL=http://localhost:10001
WASH_TRADE_AGENT_URL=http://localhost:10002
ORCHESTRATOR_HOST=localhost
ORCHESTRATOR_PORT=10000
```

## Project Structure

```
alerts/
├── pyproject.toml
├── .env.example
├── README.md
│
├── src/alerts/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Config loader (env-based)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py          # BaseAlertDecision
│   │   ├── insider_trading.py  # InsiderTradingDecision
│   │   └── wash_trade.py    # WashTradeDecision + RelationshipNetwork
│   ├── tools/               # Shared tools
│   │   ├── base.py          # Base tool with LLM helper
│   │   ├── alert_reader.py
│   │   ├── trader_history.py
│   │   ├── trader_profile.py
│   │   ├── market_news.py
│   │   ├── market_data.py
│   │   └── peer_trades.py
│   ├── agents/
│   │   ├── insider_trading/ # Insider trading agent
│   │   │   ├── __init__.py
│   │   │   ├── agent.py     # AlertAnalyzerAgent
│   │   │   └── prompts/
│   │   │       └── system_prompt.py
│   │   └── wash_trade/      # Wash trade agent
│   │       ├── __init__.py
│   │       ├── agent.py     # WashTradeAnalyzerAgent
│   │       ├── prompts/
│   │       │   └── system_prompt.py
│   │       └── tools/       # Wash-trade-specific tools
│   │           ├── account_relationships.py
│   │           ├── related_accounts_history.py
│   │           ├── trade_timing.py
│   │           └── counterparty_analysis.py
│   ├── reports/
│   │   ├── html_generator.py        # Insider trading HTML report
│   │   └── wash_trade_report.py     # Wash trade HTML with SVG network
│   └── a2a/                 # A2A protocol integration
│       ├── __init__.py
│       ├── insider_trading_executor.py
│       ├── insider_trading_server.py
│       ├── wash_trade_executor.py   # NEW: A2A executor for wash trade
│       ├── wash_trade_server.py     # NEW: A2A server for wash trade
│       ├── orchestrator.py          # Routes alerts to specialized agents
│       ├── orchestrator_executor.py
│       ├── orchestrator_server.py
│       └── test_client.py
│
├── test_data/
│   ├── alerts/
│   │   ├── alert_genuine.xml        # Insider trading test cases
│   │   ├── alert_false_positive.xml
│   │   ├── alert_ambiguous.xml
│   │   └── wash_trade/              # NEW: Wash trade test cases
│   │       ├── wash_genuine.xml
│   │       ├── wash_false_positive.xml
│   │       ├── wash_ambiguous.xml
│   │       └── wash_layered.xml
│   ├── trader_history.csv
│   ├── trader_profiles.csv
│   ├── market_news.txt
│   ├── market_data.csv
│   ├── peer_trades.csv
│   ├── few_shot_examples.json
│   ├── wash_trade/                  # NEW: Wash trade data files
│   │   ├── account_relationships.csv
│   │   └── related_accounts_history.csv
│   └── wash_trade_few_shot_examples.json  # NEW: Wash trade precedents
│
├── resources/reports/        # Output directory
│
└── tests/
    ├── conftest.py
    ├── test_tools.py
    ├── test_models.py
    ├── test_wash_trade_models.py    # NEW: Wash trade model tests
    ├── test_a2a_orchestrator.py     # Updated with wash trade routing tests
    └── test_config.py
```

## Tools

### Shared Tools (Used by All Agents)

The agents use 6 shared tools, each calling an LLM internally:

| Tool | Purpose | Returns |
|------|---------|---------|
| `read_alert` | Parse alert XML | Structured alert summary |
| `query_trader_history` | 1-year trade history | Baseline deviation analysis |
| `query_trader_profile` | Role and access level | MNPI access assessment |
| `query_market_news` | News timeline | Public information analysis |
| `query_market_data` | Price/volume data | Market conditions analysis |
| `query_peer_trades` | Peer activity | Isolation vs. consensus |

### Wash Trade-Specific Tools

The wash trade agent has 4 additional specialized tools:

| Tool | Purpose | Returns |
|------|---------|---------|
| `query_account_relationships` | Discover connected accounts | Relationship network with ownership links |
| `query_related_accounts_history` | Cross-account trading patterns | Coordinated activity analysis |
| `query_trade_timing` | Sub-second timing analysis | Pre-arrangement pattern detection |
| `query_counterparty_analysis` | Counterparty matching | Beneficial ownership overlap assessment |

## Few-Shot Examples

The system uses a "case law" approach where few-shot examples serve as precedents. Each agent type has its own examples file.

### Insider Trading Examples (`test_data/few_shot_examples.json`)
- Clear genuine insider trading (ESCALATE)
- Clear false positive (CLOSE)
- Subtle genuine case (ESCALATE)
- Subtle false positive (CLOSE)
- Ambiguous/conflicting signals (NEEDS_HUMAN_REVIEW)
- Indirect information leak (ESCALATE)

### Wash Trade Examples (`test_data/wash_trade_few_shot_examples.json`)
- Same beneficial owner - genuine wash trade (ESCALATE)
- Market maker legitimate activity (CLOSE)
- Coordinated timing patterns (ESCALATE)
- Index rebalancing false positive (CLOSE)
- Layered circular trades A→B→C→A (ESCALATE)
- Mixed signals with partial ownership (NEEDS_HUMAN_REVIEW)

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=alerts

# Run specific test file
pytest tests/test_tools.py -v
```

## Architecture

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

## Output Schema

### Insider Trading Decision (`InsiderTradingDecision`)

- `alert_id`: Unique identifier
- `determination`: ESCALATE | CLOSE | NEEDS_HUMAN_REVIEW
- `genuine_alert_confidence`: 0-100 score
- `false_positive_confidence`: 0-100 score
- `key_findings`: Investigation findings
- `favorable_indicators`: Factors suggesting genuine insider trading
- `risk_mitigating_factors`: Factors suggesting false positive
- `trader_baseline_analysis`: Deviation from normal trading
- `market_context`: News, volatility, peer activity
- `reasoning_narrative`: Human-readable explanation
- `similar_precedent`: Which example case this resembles
- `recommended_action`: ESCALATE | CLOSE | MONITOR | REQUEST_MORE_DATA
- `data_gaps`: Missing information

### Wash Trade Decision (`WashTradeDecision`)

- `alert_id`: Unique identifier
- `determination`: ESCALATE | CLOSE | NEEDS_HUMAN_REVIEW
- `genuine_alert_confidence`: 0-100 score
- `false_positive_confidence`: 0-100 score
- `key_findings`: Investigation findings
- `favorable_indicators`: Factors suggesting genuine wash trading
- `risk_mitigating_factors`: Factors suggesting legitimate activity
- `relationship_network`: Graph structure with nodes (accounts) and edges (relationships)
- `timing_patterns`: List of detected timing patterns (timestamp, interval, pattern type)
- `trade_flows`: Circular trade flow detection results
- `counterparty_patterns`: Counterparty matching analysis
- `historical_pattern_summary`: 90-day pattern analysis
- `regulatory_framework`: Applicable regulations (MAS SFA, SFC SFO, etc.)
- `reasoning_narrative`: Human-readable explanation
- `similar_precedent`: Which example case this resembles
- `recommended_action`: ESCALATE | CLOSE | MONITOR | REQUEST_MORE_DATA
- `data_gaps`: Missing information

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent framework | LangGraph | Battle-tested, good tool support |
| Architecture | Multi-agent with orchestrator | Specialized agents for different alert types |
| Inter-agent protocol | A2A (Agent-to-Agent) | Google's standard for agent communication |
| Tool LLM calls | Each tool calls LLM | Better accuracy through focused interpretation |
| Scoring approach | Pure LLM reasoning | Adaptable via few-shot examples |
| Error handling | Fail-fast | Crash loudly for debugging |
| LLM provider | Config-driven | Flexibility for enterprise deployment |
| Regulatory framework | APAC-focused | Supports MAS SFA, SFC SFO, ASIC, FSA FIEA |

## Future Enhancements

- [ ] Feedback loop: Human decisions become new examples
- [ ] Ground truth validation against labeled data
- [ ] Calendar events tool for earnings/event correlation
- [ ] Internal communications tool
- [ ] Async processing for higher volume
- [ ] Web UI for compliance analysts
