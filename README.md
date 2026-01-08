# SMARTS Alert False Positive Analyzer

An intelligent compliance filter that analyzes SMARTS surveillance alerts to reduce false positive rates before escalating to human compliance analysts. The system uses a deterministic multi-agent architecture with pure LLM-based reasoning.

## Overview

This system supports multiple alert types through specialized agents:
- **Insider Trading Alerts**: Pre-announcement trading, MNPI-based trades
- **Wash Trade Alerts**: Same beneficial ownership, pre-arranged execution, circular flows

The system automates initial analysis by:
- Receiving pre-aggregated data from Big Data Layer
- Executing tools in fixed order (deterministic, no LLM routing)
- Using LLM interpretation at each step to extract insights
- Applying "case law" reasoning via few-shot examples
- Producing structured decisions with detailed reasoning

## Key Features

- **Deterministic Execution**: Fixed tool order, predictable and reproducible
- **Proactive Data Flow**: Big Data Layer provides all data upfront
- **Pure LLM Reasoning**: No hardcoded scoring weights
- **Multi-Agent Architecture**: Specialized agents for different alert types
- **Real-Time Web UI**: Live execution DAG with SSE streaming
- **12 Specialized Tools**: Each calls LLM internally for interpretation
- **Few-Shot Learning**: Examples in external JSON for zero-code tuning
- **Professional Reports**: JSON + HTML (Tailwind CSS) with network graphs
- **Audit Trail**: All decisions logged for compliance
- **APAC Regulatory Framework**: MAS SFA, SFC SFO, ASIC, FSA FIEA

## Quick Start

### Prerequisites

- Python 3.10+
- LLM API key (OpenAI, Azure OpenAI, OpenRouter, or Google Gemini)

### Installation

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
# Edit .env with your API key and model
```

### Configuration

Edit `.env` file:

```bash
# LLM Provider: "openai", "azure", "openrouter", or "gemini"
LLM_PROVIDER=openai

# OpenAI Configuration
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Paths
DATA_DIR=test_data
OUTPUT_DIR=resources/reports

# Logging
LOG_LEVEL=INFO
```

## Usage

### Option 1: CLI (Single Alert Analysis)

```bash
# Analyze the default genuine insider trading case
python -m alerts.main

# Analyze a specific alert file
python -m alerts.main --alert test_data/alerts/alert_genuine.xml

# Analyze wash trade alert
python -m alerts.main --alert test_data/alerts/wash_trade/wash_genuine.xml

# Run with verbose logging
python -m alerts.main --verbose
```

**Output**:
- `resources/reports/decision_{alert_id}.json` - Full decision JSON
- `resources/reports/decision_{alert_id}.html` - Professional HTML report
- `resources/reports/audit_log.jsonl` - Append-only audit trail

### Option 2: Web UI (Multi-Agent with Real-Time Streaming)

**Quick Start - All Servers in Background**:
```bash
bash scripts/start_all_servers.sh
# Open browser: http://localhost:8080
# Logs: logs/{insider_trading,wash_trade,orchestrator,frontend}.log
```

**Manual Setup (4 terminals)**:

```bash
# Terminal 1 - Insider Trading Agent
python -m alerts.a2a.insider_trading_server --port 10001

# Terminal 2 - Wash Trade Agent
python -m alerts.a2a.wash_trade_server --port 10002

# Terminal 3 - Orchestrator
python -m alerts.a2a.orchestrator_server --port 10000

# Terminal 4 - Frontend UI
python -m frontend.app --port 8080
```

Then open `http://localhost:8080` in your browser.

**Web UI Features**:
- Drag-and-drop XML alert upload
- Real-time execution DAG (User → Orchestrator → Agent → Tools → Output)
- SSE-based progress timeline with tool execution events
- Dynamic results rendering with confidence scores
- Interactive Cytoscape.js network graphs for wash trade analysis
- Download JSON and HTML reports

## Architecture

### System Flow (Deterministic)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Big Data Layer (External)                    │
│  Aggregates all required data from production systems           │
└───────────────────────┬─────────────────────────────────────────┘
                        │ AnalysisRequest (pre-aggregated data)
                        ▼
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
│   5 tools (fixed order)   │   │   7 tools (fixed order)       │
│   No LLM routing          │   │   No LLM routing              │
└───────────────────────────┘   └───────────────────────────────┘
```

### Deterministic Execution

Each agent executes tools in a **fixed order** defined in `TOOL_ORDER` tuple:

**Insider Trading Agent**:
1. alert_reader
2. market_news
3. market_data
4. trader_profile
5. trader_history

**Wash Trade Agent**:
1. alert_reader
2. account_relationships
3. related_accounts_history
4. trade_timing
5. market_data
6. trader_profile
7. counterparty_analysis

**No LLM-based routing** - predictable and reproducible execution.

### Decision Outcomes

| Determination | Condition | Action |
|---------------|-----------|--------|
| `ESCALATE` | High confidence of genuine violation | Route to compliance analyst |
| `CLOSE` | High confidence of false positive | Auto-close with documentation |
| `NEEDS_HUMAN_REVIEW` | Conflicting signals, cannot decide | Route for human judgment |

### Tool Architecture

**Common Tools** (all agents):
- `alert_reader` - Parse alert XML
- `trader_profile` - Role and MNPI access level
- `market_data` - Price/volume data analysis

**Insider Trading Tools**:
- `trader_history` - 1-year trade baseline
- `market_news` - News timeline

**Wash Trade Tools**:
- `account_relationships` - Ownership network
- `related_accounts_history` - Cross-account patterns
- `trade_timing` - Sub-second timing analysis
- `counterparty_analysis` - Beneficial ownership overlap

**Tool Design**: Each tool calls an LLM internally to interpret raw data and return insights (not raw data).

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=alerts

# Run specific test file
pytest tests/test_tools.py -v
```

## LLM Provider Support

Switch between providers by setting `LLM_PROVIDER` in `.env`:

**OpenAI**:
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

**Azure OpenAI**:
```bash
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

**OpenRouter**:
```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openai/gpt-4o  # Or any model in catalog
```

**Google Gemini**:
```bash
LLM_PROVIDER=gemini
GOOGLE_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash
```

## Tuning Agent Behavior

The system uses a "case law" approach where few-shot examples serve as precedents. To tune behavior:

**No code changes needed** - just edit the examples:
- Insider Trading: `test_data/few_shot_examples.json`
- Wash Trade: `test_data/wash_trade_few_shot_examples.json`

Add new example scenarios with detailed reasoning. The agent compares current cases to precedents.

## Project Structure

```
alerts/
├── src/alerts/              # Backend analysis engine
│   ├── agents/              # IT and WT deterministic agents
│   ├── tools/               # Common tools + agent-specific tools
│   ├── models/              # Pydantic schemas (request + output)
│   ├── reports/             # HTML/JSON report generators
│   └── a2a/                 # A2A protocol servers
├── src/frontend/            # FastAPI web UI
│   ├── templates/           # HTML templates
│   └── static/              # JavaScript, CSS
├── test_data/               # Alert XMLs, CSVs, few-shot examples
├── tests/                   # pytest test suite
├── scripts/                 # start_all_servers.sh, test scripts
└── resources/reports/       # Output directory
```

## API Contract (Big Data Layer)

### Request Model

```python
class AnalysisRequest:
    alert_id: str
    agent_type: "insider_trading" | "wash_trade"
    tool_data: Dict[str, ToolInput]

class ToolInput:
    format: "xml" | "csv" | "txt"
    data: str  # Raw content
```

### Required Tools per Agent

**Insider Trading**:
- `alert_reader`, `market_news`, `market_data`, `trader_profile`, `trader_history`

**Wash Trade**:
- `alert_reader`, `market_data`, `trader_profile`, `account_relationships`, `related_accounts_history`, `trade_timing`, `counterparty_analysis`

**Validation**: Missing required tools → immediate failure (fail-fast)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Execution | Deterministic (fixed tool order) | Predictable, reproducible, testable |
| Data flow | Proactive (pre-aggregated) | Decouples data layer, scales to production |
| Agent framework | Custom loop (no LangGraph) | Simplicity, full control, no overhead |
| Inter-agent protocol | A2A (Agent-to-Agent) | Google's standard for agent communication |
| Tool LLM calls | Each tool calls LLM | Better accuracy through focused interpretation |
| Scoring approach | Pure LLM reasoning | Adaptable via few-shot examples |
| Error handling | Fail-fast | Crash loudly for debugging |
| LLM provider | Config-driven | Flexibility for enterprise deployment |

## Development

See `CLAUDE.md` for:
- Detailed architecture documentation
- Development patterns (adding tools, agents, events)
- Directory index with file purposes
- Integration points and configuration
- Testing strategy

## License

MIT
