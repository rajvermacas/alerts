# SMARTS Alert False Positive Analyzer

An intelligent compliance filter that uses multi-agent LLM architecture to analyze SMARTS surveillance alerts and reduce false positive rates. The system employs pure agentic reasoning without hardcoded scoring, enabling behavior tuning through examples rather than code changes.

## Features

- **Multi-Agent Architecture**: Specialized agents for Insider Trading and Wash Trade alerts
- **Proactive Data Flow**: All data pre-aggregated and injected for efficient analysis
- **Real-Time Web UI**: Live execution DAG with SSE streaming progress
- **Parallel Tool Execution**: 9 specialized tools running concurrently
- **Two-Tier LLM Interpretation**: Tools interpret data, agents reason over insights
- **Few-Shot Learning**: Behavior tuning via external JSON examples (no code changes)
- **Professional Reports**: JSON + HTML output with network visualizations
- **APAC Regulatory Framework**: Supports MAS SFA, SFC SFO, ASIC, FSA FIEA
- **Audit Trail**: Complete decision logging for compliance tracking

## Quick Start

### Prerequisites

- Python 3.10+
- LLM API key (OpenAI, Azure OpenAI, OpenRouter, or Google Gemini)

### Installation

```bash
# Clone repository
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
│   5 tools (3 + 2)         │   │   7 tools (3 + 4)             │
└───────────────────────────┘   └───────────────────────────────┘
```

### Proactive Data Flow

```
BigDataSimulator → AnalysisRequest → Agent → Tools (parallel) → Decision
    (POC mock)     (all data injected)
```

**Key Innovation**: Tools don't load data themselves. All data is pre-aggregated by the Big Data Layer and injected via `AnalysisRequest`. This enables:
- Parallel tool execution
- Clean separation of concerns
- Easy production transition (replace simulator with DB/API client)
- Tools remain unchanged regardless of data source

### Decision Outcomes

| Determination | Condition | Action |
|---------------|-----------|--------|
| `ESCALATE` | High confidence of genuine violation | Route to compliance analyst |
| `CLOSE` | High confidence of false positive | Auto-close with documentation |
| `NEEDS_HUMAN_REVIEW` | Conflicting signals, cannot decide | Route for human judgment |

### Tools

**Common Tools** (used by all agents):
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

Each tool calls an LLM internally to interpret raw data and return insights (not raw data).

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=alerts

# Run specific test file
pytest tests/test_tools.py -v

# Run wash trade tests
pytest -k "wash_trade" -v
```

## LLM Provider Support

Switch between providers by setting `LLM_PROVIDER` in `.env`:

### OpenAI
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

### Azure OpenAI
```bash
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

### OpenRouter
```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openai/gpt-4o  # Or any model in catalog
```

### Google Gemini
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
│   ├── agents/              # IT and WT specialized agents
│   ├── tools/common/        # Shared tools (BaseTool, alert_reader, etc.)
│   ├── models/              # Pydantic output schemas + AnalysisRequest
│   ├── reports/             # HTML/JSON report generators
│   ├── a2a/                 # A2A protocol servers (orchestrator + agents)
│   └── mock/                # BigDataSimulator (POC)
├── src/frontend/            # FastAPI web UI
│   ├── templates/           # HTML templates
│   └── static/              # JavaScript, CSS
├── test_data/               # Alert XMLs, CSVs, few-shot examples
├── tests/                   # pytest test suite
├── scripts/                 # start_all_servers.sh, test scripts
└── resources/reports/       # Output directory
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent framework | LangGraph | Battle-tested, excellent tool support |
| Architecture | Multi-agent with orchestrator | Specialized agents for different alert types |
| Inter-agent protocol | A2A (Agent-to-Agent) | Google's standard for agent communication |
| Data flow | Proactive (injected) | Enables parallel execution, clean separation |
| Tool LLM calls | Each tool calls LLM | Better accuracy through focused interpretation |
| Scoring approach | Pure LLM reasoning | Adaptable via few-shot examples |
| Error handling | Fail-fast | Crash loudly for debugging (POC phase) |
| LLM provider | Config-driven | Flexibility for enterprise deployment |

## Development

See `CLAUDE.md` for:
- Detailed architecture documentation
- Development patterns (adding tools, agents, events)
- Directory index with file purposes
- Integration points and configuration
- Testing strategy
- Key constraints and anti-patterns

## License

MIT
