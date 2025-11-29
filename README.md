# SMARTS Alert False Positive Analyzer

An intelligent compliance filter that analyzes SMARTS surveillance alerts to reduce false positive rates before escalating to human compliance analysts. The system uses a fully agentic LLM-based approach with no hardcoded scoring weights.

## Overview

This POC system automates the initial analysis of insider trading alerts by:
- Reading SMARTS alert XML files
- Gathering evidence from multiple data sources (trader history, profiles, market data, news, peer activity)
- Using LLM interpretation at each tool to extract insights (not raw data)
- Applying "case law" reasoning by comparing to few-shot precedent examples
- Producing structured decisions with detailed reasoning

## Features

- **Fully Agentic**: Pure LLM reasoning without deterministic scoring
- **6 Specialized Tools**: Each tool calls LLM internally to interpret data
- **Few-Shot Learning**: Examples stored in external JSON for easy tuning
- **Structured Output**: Pydantic models ensure consistent, parseable decisions
- **Audit Trail**: All decisions logged for compliance tracking
- **Fail-Fast**: No graceful degradation; errors crash loudly for debugging

## Decision Outcomes

| Determination | Condition | Action |
|---------------|-----------|--------|
| `ESCALATE` | High confidence of genuine insider trading | Route to compliance analyst |
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
│   ├── agent.py             # LangGraph agent
│   ├── models.py            # Pydantic output models
│   ├── tools/
│   │   ├── base.py          # Base tool with LLM helper
│   │   ├── alert_reader.py  # read_alert tool
│   │   ├── trader_history.py
│   │   ├── trader_profile.py
│   │   ├── market_news.py
│   │   ├── market_data.py
│   │   └── peer_trades.py
│   └── prompts/
│       └── system_prompt.py # Agent system prompt
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
├── resources/reports/        # Output directory
│
└── tests/
    ├── conftest.py
    ├── test_tools.py
    ├── test_models.py
    └── test_config.py
```

## Tools

The agent uses 6 specialized tools, each calling an LLM internally:

| Tool | Purpose | Returns |
|------|---------|---------|
| `read_alert` | Parse alert XML | Structured alert summary |
| `query_trader_history` | 1-year trade history | Baseline deviation analysis |
| `query_trader_profile` | Role and access level | MNPI access assessment |
| `query_market_news` | News timeline | Public information analysis |
| `query_market_data` | Price/volume data | Market conditions analysis |
| `query_peer_trades` | Peer activity | Isolation vs. consensus |

## Few-Shot Examples

The system uses a "case law" approach where few-shot examples serve as precedents. Edit `test_data/few_shot_examples.json` to tune behavior without code changes.

Example scenarios included:
- Clear genuine insider trading (ESCALATE)
- Clear false positive (CLOSE)
- Subtle genuine case (ESCALATE)
- Subtle false positive (CLOSE)
- Ambiguous/conflicting signals (NEEDS_HUMAN_REVIEW)
- Indirect information leak (ESCALATE)

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

The structured decision includes:
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

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent framework | LangGraph | Battle-tested, good tool support |
| Number of agents | Single agent | Simpler for POC |
| Tool LLM calls | Each tool calls LLM | Better accuracy through focused interpretation |
| Scoring approach | Pure LLM reasoning | Adaptable via few-shot examples |
| Error handling | Fail-fast | Crash loudly for debugging |
| LLM provider | Config-driven | Flexibility for enterprise deployment |

## Future Enhancements

- [ ] Feedback loop: Human decisions become new examples
- [ ] Ground truth validation against labeled data
- [ ] Calendar events tool for earnings/event correlation
- [ ] Internal communications tool
- [ ] Async processing for higher volume
- [ ] Web UI for compliance analysts
