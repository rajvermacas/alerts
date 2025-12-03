# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SMARTS Alert False Positive Analyzer - An intelligent compliance filter that analyzes SMARTS surveillance alerts for potential insider trading and wash trading violations. Uses a fully agentic LLM-based approach with LangGraph, where each tool calls an LLM internally to interpret data rather than returning raw data.

**Core Philosophy**: Fully agentic reasoning without hardcoded scoring weights. Adaptability through few-shot examples stored in external JSON files (not code changes).

**Supported Alert Types**:
- **Insider Trading**: Pre-announcement trading, MNPI-based trades
- **Wash Trading**: Same beneficial ownership, pre-arranged execution, circular trade flows (A→B→C→A)

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys (NEVER commit .env)
```

### Running the Application
```bash
# Analyze the default alert (genuine insider trading case)
python -m alerts.main

# Analyze a specific alert file
python -m alerts.main --alert test_data/alerts/alert_genuine.xml
python -m alerts.main --alert test_data/alerts/alert_false_positive.xml
python -m alerts.main --alert test_data/alerts/alert_ambiguous.xml

# Run with verbose logging
python -m alerts.main --verbose

# Run with minimal output
python -m alerts.main --quiet

# Using installed script entry point
alerts
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=alerts

# Run specific test file
pytest tests/test_tools.py -v

# Run a single test function
pytest tests/test_tools.py::test_alert_reader_tool -v

# Run tests matching a keyword
pytest -k "wash_trade" -v

# Run with verbose output and short traceback
pytest -v --tb=short
```

### Web UI (Frontend)
```bash
# Start all required servers (4 terminals)

# Terminal 1: Insider Trading Agent
python -m alerts.a2a.insider_trading_server --port 10001

# Terminal 2: Wash Trade Agent
python -m alerts.a2a.wash_trade_server --port 10002

# Terminal 3: Orchestrator
python -m alerts.a2a.orchestrator_server --port 10000

# Terminal 4: Frontend UI
python -m frontend.app --port 8080

# Open browser: http://localhost:8080
```

## Architecture

### High-Level Design Pattern

**Multi-Agent Architecture** with orchestrator routing to specialized agents:
- **Orchestrator Agent**: Routes alerts to appropriate specialized agent
- **Insider Trading Agent**: 6 shared tools for MNPI/pre-announcement analysis
- **Wash Trade Agent**: 6 shared tools + 4 wash-trade-specific tools

Each tool:
1. Reads from a data source (CSV/XML/TXT files in POC)
2. **Calls LLM internally** to interpret raw data
3. Returns **insights** (not raw data) to the main agent

This creates a **two-tier LLM architecture**:
- **Tier 1**: Tool-level LLMs extract insights from raw data
- **Tier 2**: Main agent LLM makes final determination using tool insights + few-shot examples

### Core Components

```
src/
├── alerts/                      # Backend analysis engine
│   ├── main.py                  # CLI entry point, LLM initialization
│   ├── config.py                # Environment-based configuration (OpenAI/Azure/OpenRouter)
│   ├── models/
│   │   ├── base.py              # BaseAlertDecision
│   │   ├── insider_trading.py   # InsiderTradingDecision
│   │   └── wash_trade.py        # WashTradeDecision + RelationshipNetwork
│   ├── tools/                   # Shared tools (used by all agents)
│   │   ├── base.py              # BaseTool class with LLM interpretation
│   │   ├── alert_reader.py
│   │   ├── trader_history.py
│   │   ├── trader_profile.py
│   │   ├── market_news.py
│   │   ├── market_data.py
│   │   └── peer_trades.py
│   ├── agents/
│   │   ├── insider_trading/     # Insider trading agent
│   │   │   ├── agent.py         # AlertAnalyzerAgent
│   │   │   └── prompts/
│   │   │       └── system_prompt.py
│   │   └── wash_trade/          # Wash trade agent
│   │       ├── agent.py         # WashTradeAnalyzerAgent
│   │       ├── prompts/
│   │       │   └── system_prompt.py
│   │       └── tools/           # Wash-trade-specific tools
│   │           ├── account_relationships.py
│   │           ├── related_accounts_history.py
│   │           ├── trade_timing.py
│   │           └── counterparty_analysis.py
│   ├── reports/
│   │   ├── html_generator.py    # Insider trading HTML report
│   │   └── wash_trade_report.py # Wash trade HTML with SVG network
│   └── a2a/                     # A2A (Agent-to-Agent) protocol integration
│       ├── insider_trading_executor.py
│       ├── insider_trading_server.py
│       ├── wash_trade_executor.py
│       ├── wash_trade_server.py
│       ├── orchestrator.py      # Routes alerts to specialized agents
│       ├── orchestrator_executor.py
│       ├── orchestrator_server.py
│       └── test_client.py
│
└── frontend/                    # Web UI (FastAPI + HTMX)
    ├── app.py                   # FastAPI routes, A2A client integration
    ├── task_manager.py          # In-memory task tracking
    ├── templates/
    │   ├── base.html            # Base template with Tailwind CSS
    │   └── upload.html          # Upload page with all UI states
    └── static/
        ├── css/styles.css       # Custom styles (animations, accessibility)
        └── js/
            ├── upload.js        # File upload and drag-drop handling
            ├── polling.js       # Status polling (2s interval)
            └── results.js       # Results rendering + Cytoscape.js graph
```

### A2A (Agent-to-Agent) Protocol Integration

The system supports Google's A2A protocol for agent-to-agent communication, enabling an orchestrator pattern where a central agent routes alerts to specialized agents.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                 Orchestrator Agent (Port 10000)                 │
│  (Reads alerts, determines type, routes to specialized agents)  │
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

**Running A2A Servers:**
```bash
# Terminal 1: Start the insider trading agent server
python -m alerts.a2a.insider_trading_server --port 10001

# Terminal 2: Start the wash trade agent server
python -m alerts.a2a.wash_trade_server --port 10002

# Terminal 3: Start the orchestrator server
python -m alerts.a2a.orchestrator_server --port 10000

# Terminal 4: Test with the client
python -m alerts.a2a.test_client --server-url http://localhost:10000 \
    --alert test_data/alerts/alert_genuine.xml

# Test wash trade alert
python -m alerts.a2a.test_client --server-url http://localhost:10000 \
    --alert test_data/alerts/wash_trade/wash_genuine.xml
```

**Using installed script entry points:**
```bash
alerts-insider-trading-server --port 10001
alerts-wash-trade-server --port 10002
alerts-orchestrator-server --port 10000 \
    --insider-trading-url http://localhost:10001 \
    --wash-trade-url http://localhost:10002
```

**Key A2A Concepts:**
- **AgentCard**: JSON document at `/.well-known/agent.json` describing agent capabilities
- **AgentExecutor**: Handles incoming A2A requests and executes agent logic
- **Task**: Core abstraction for tracking long-running operations
- **A2AClient**: Client for communicating with remote A2A agents

**Flow:**
1. User sends alert to Orchestrator via A2A
2. Orchestrator reads alert XML to determine type (insider trading, wash trade, or unsupported)
3. If insider trading → routes to Insider Trading Agent via A2A
4. If wash trade → routes to Wash Trade Agent via A2A
5. Specialized agent analyzes and returns decision
6. Orchestrator returns result to user

**Alert Type Detection:**
- **Insider Trading**: Alert types containing "insider", "pre-announcement", "mnpi", "material"
- **Wash Trade**: Alert types containing "wash", "self-trade", "matched order", "circular"

### LangGraph Workflow

```
START → agent → tools? → [tools → agent]* → respond → END
        ↑                                      ↓
        └──────── loops until no tool calls ───┘
```

**Nodes**:
- `agent`: Main reasoning node (decides which tools to call)
- `tools`: ToolNode executing requested tools
- `respond`: Final structured output generation using `AlertDecision` Pydantic model

**Key Implementation Details**:
- `MessagesState` for conversation history
- `recursion_limit=50` to allow multiple tool calls
- Tools bound to LLM via `llm.bind_tools()`
- Final response uses `llm.with_structured_output(AlertDecision)`

### Tool Implementation Pattern

All tools inherit from `BaseTool` and implement:

```python
class SomeTool(BaseTool):
    def _load_data(self, **kwargs) -> str:
        # Read from data source (CSV, XML, etc.)
        pass

    def _build_interpretation_prompt(self, raw_data: str, **kwargs) -> str:
        # Build LLM prompt for interpretation
        pass

    def __call__(self, **kwargs) -> str:
        # BaseTool handles: load → interpret with LLM → return insights
        pass
```

**Critical**: Tools return LLM-interpreted insights, NOT raw data. Example:
```
Bad:  "trader_history.csv has 247 rows..."
Good: "This trader typically trades 5K shares/day in tech sector.
       The flagged 50K share healthcare trade is 10x normal volume
       and a sector they've never touched."
```

### Few-Shot Examples Strategy

Each agent type has its own examples file:
- **Insider Trading**: `test_data/few_shot_examples.json`
- **Wash Trade**: `test_data/wash_trade_few_shot_examples.json`

The agent uses a **"case law" approach** - few-shot examples serve as precedents. To tune behavior:
1. Edit the appropriate examples file (NO code changes needed)
2. Add new example scenarios with detailed reasoning
3. Agent compares current case to precedents

Loaded via each agent's `system_prompt.py:load_few_shot_examples()` and injected into system prompt.

### Configuration Management

**Environment-based** configuration supporting OpenAI, Azure OpenAI, and OpenRouter:

```python
# config.py uses dataclasses with fail-fast validation
AppConfig
├── LLMConfig       # Provider, model, API keys, temperature
├── DataConfig      # Paths to data_dir, output_dir, alerts
└── LoggingConfig   # Log level, format, optional file
```

Load with: `get_config()` (reads from `.env` file via `python-dotenv`)

**Provider switching**: Set `LLM_PROVIDER=openai`, `LLM_PROVIDER=azure`, or `LLM_PROVIDER=openrouter` in `.env`

### Output Schema

**Insider Trading Decision** (`InsiderTradingDecision`):
- `determination`: "ESCALATE" | "CLOSE" | "NEEDS_HUMAN_REVIEW"
- `genuine_alert_confidence`: 0-100
- `false_positive_confidence`: 0-100
- `key_findings`: List[str]
- `favorable_indicators`: Reasons suggesting genuine insider trading
- `risk_mitigating_factors`: Reasons suggesting false positive
- `trader_baseline_analysis`: TraderBaselineAnalysis nested model
- `market_context`: MarketContext nested model
- `reasoning_narrative`: 2-4 paragraph explanation
- `similar_precedent`: Which few-shot example this resembles

**Wash Trade Decision** (`WashTradeDecision`):
- `determination`: "ESCALATE" | "CLOSE" | "NEEDS_HUMAN_REVIEW"
- `genuine_alert_confidence`: 0-100
- `false_positive_confidence`: 0-100
- `key_findings`: List[str]
- `favorable_indicators`: Reasons suggesting genuine wash trading
- `risk_mitigating_factors`: Reasons suggesting legitimate activity
- `relationship_network`: RelationshipNetwork (nodes + edges for visualization)
- `timing_patterns`: List[TimingPattern] - sub-second timing analysis
- `trade_flows`: List[TradeFlow] - circular flow detection (A→B→C→A)
- `counterparty_patterns`: List[CounterpartyPattern] - matching analysis
- `historical_pattern_summary`: HistoricalPatternSummary - 90-day patterns
- `regulatory_framework`: Applicable APAC regulations (MAS SFA, SFC SFO, etc.)
- `reasoning_narrative`: 2-4 paragraph explanation
- `similar_precedent`: Which few-shot example this resembles

**Output Files**:
- `resources/reports/decision_{alert_id}.json` - Full decision JSON
- `resources/reports/decision_{alert_id}.html` - Professional HTML report with Tailwind CSS
- `resources/reports/audit_log.jsonl` - Append-only audit trail

## Important Constraints

### Error Handling Philosophy
**Fail-fast**: No graceful degradation. Errors crash loudly for debugging. If a tool fails, the entire analysis fails.

Rationale: In POC phase, we want immediate feedback on issues rather than silent failures.

### Data Access in POC
All data sources are **local files** in `test_data/`:
- `alerts/*.xml` - Insider trading SMARTS alert files
- `alerts/wash_trade/*.xml` - Wash trade SMARTS alert files
- `trader_history.csv` - Historical trades
- `trader_profiles.csv` - Trader roles/access levels
- `market_news.txt` - News timeline (free-form text)
- `market_data.csv` - Price/volume data
- `peer_trades.csv` - Peer trading activity
- `few_shot_examples.json` - Insider trading few-shot precedents
- `wash_trade_few_shot_examples.json` - Wash trade few-shot precedents
- `wash_trade/account_relationships.csv` - Account relationship data
- `wash_trade/related_accounts_history.csv` - Cross-account trade history

### LLM Provider Support

Code is **provider-agnostic**. Switch between three providers via configuration:

**OpenAI**:
- Environment variables: `OPENAI_API_KEY` + `OPENAI_MODEL`
- Models: Any OpenAI model (e.g., "gpt-4o", "gpt-4-turbo")

**Azure OpenAI**:
- Environment variables: `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` + `AZURE_OPENAI_API_VERSION`
- Models: Any deployed model in Azure

**OpenRouter** (NEW):
- Environment variables: `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`
- Optional: `OPENROUTER_SITE_URL` + `OPENROUTER_SITE_NAME` (for site ranking)
- Models: Any model in OpenRouter catalog (e.g., "openai/gpt-4o", "anthropic/claude-opus", "meta-llama/llama-3-8b")
- Base URL: Automatically set to `https://openrouter.ai/api/v1`

Implementation: `main.py:create_llm()` uses LangChain's `ChatOpenAI` or `AzureChatOpenAI`. OpenRouter also uses `ChatOpenAI` with OpenAI-compatible API.

**Example OpenRouter Usage**:
```bash
export LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY=sk-or-...
export OPENROUTER_MODEL=anthropic/claude-opus  # Or any other model
python -m alerts.main
```

### No Hardcoded Scoring
The system uses **pure LLM reasoning** - no weight-based scoring formulas. To adjust behavior:
1. Modify few-shot examples in the appropriate JSON file:
   - Insider trading: `test_data/few_shot_examples.json`
   - Wash trade: `test_data/wash_trade_few_shot_examples.json`
2. Update system prompt in the appropriate agent's `prompts/system_prompt.py`

**Do NOT add** scoring weights, thresholds, or rule-based logic.

## Development Patterns

### Adding a New Tool

**Shared tools** (used by all agents):
1. Create tool class in `src/alerts/tools/your_tool.py`
2. Inherit from `BaseTool`
3. Implement `_load_data()` and `_build_interpretation_prompt()`
4. Add to each agent's `_create_tool_instances()` method
5. Update tests in `tests/test_tools.py`

**Agent-specific tools** (e.g., wash trade tools):
1. Create tool class in `src/alerts/agents/{agent_type}/tools/your_tool.py`
2. Inherit from `BaseTool`
3. Implement `_load_data()` and `_build_interpretation_prompt()`
4. Add to the specific agent's `_create_tool_instances()` method
5. Update tests in `tests/test_{agent_type}_tools.py`

### Modifying Agent Behavior
1. **First choice**: Edit the appropriate few-shot examples JSON file (no code changes)
2. **If insufficient**: Update system prompt in the agent's `prompts/system_prompt.py`
3. **Last resort**: Modify agent graph in the agent's `agent.py:_build_graph()`

### Testing Strategy
- Unit tests for tools, models, config, HTML generation
- Mock LLM responses for deterministic tests
- Use `conftest.py` for shared fixtures
- Test data generation scripts go in `scripts/` folder (currently empty)
- HTML report tests verify Tailwind CSS output and structure

### Web UI Frontend

The system includes a web interface for uploading alerts and viewing results:

**Architecture:**
```
Browser (http://localhost:8080)
    │
    ├── POST /api/analyze (multipart XML upload)
    ├── GET /api/status/{task_id} (2s polling)
    └── GET /api/download/{task_id}/{json|html}
    │
    ▼
FastAPI Frontend Service (Port 8080)
    │
    └── A2A Protocol (JSON-RPC over HTTP)
    │
    ▼
Orchestrator Agent (Port 10000)
    ├── Insider Trading Agent (Port 10001)
    └── Wash Trade Agent (Port 10002)
```

**Key Components:**
- `frontend/app.py`: FastAPI routes, A2A client, response parsing
- `frontend/task_manager.py`: In-memory task tracking (POC - no persistence)
- `frontend/static/js/results.js`: Dynamic rendering + Cytoscape.js graph for wash trade

**A2A Response Parsing Challenge:**
The orchestrator wraps agent responses, creating nested JSON-RPC structures. The `extract_decision_from_response()` function handles this by:
1. Detecting nested responses in artifact text
2. Extracting embedded JSON-RPC using brace matching
3. Finding artifacts ending in `_json` (e.g., `alert_decision_json`)

Debug files are saved to `resources/debug/a2a_response_*.json` for investigation.

### HTML Report Generation

The system generates professional HTML reports using Tailwind CSS:

**Insider Trading Reports** (`reports/html_generator.py:HTMLReportGenerator`):
- Split-screen layout: Original alert data (left) + AI analysis (right)
- Color-coded determination badges (ESCALATE=red, CLOSE=green, NEEDS_HUMAN_REVIEW=yellow)
- Confidence score visualization with progress bars
- Expandable sections for detailed findings
- Timeline view for trader baseline and market context
- Professional styling suitable for compliance documentation

**Wash Trade Reports** (`reports/wash_trade_report.py:WashTradeHTMLReportGenerator`):
- All features of insider trading reports, plus:
- **SVG Relationship Network**: Interactive visualization of account relationships
- Timing pattern analysis with sub-second precision
- Circular trade flow visualization (A→B→C→A detection)
- Counterparty pattern analysis
- APAC regulatory framework references (MAS SFA, SFC SFO, ASIC, FSA FIEA)

The HTML reports are generated automatically alongside JSON output and include:
- Alert metadata and details
- AI determination with confidence scores
- Key findings and evidence
- Agent-specific analysis (trader baseline for IT, relationship network for WT)
- Market context with news timeline
- Complete reasoning narrative

### Logging
Extensive logging at INFO level by default:
- Tool calls and processing times
- Agent reasoning steps
- Decision generation
- Output file writes (JSON + HTML)

Third-party loggers (httpx, openai) suppressed to WARNING level.

## Key Files Reference

| File | Purpose | When to Modify |
|------|---------|----------------|
| `test_data/few_shot_examples.json` | Insider trading behavior tuning | Adjust IT agent decision patterns |
| `test_data/wash_trade_few_shot_examples.json` | Wash trade behavior tuning | Adjust WT agent decision patterns |
| `agents/insider_trading/prompts/system_prompt.py` | IT agent instructions | Change IT reasoning approach |
| `agents/wash_trade/prompts/system_prompt.py` | WT agent instructions | Change WT reasoning approach |
| `agents/insider_trading/agent.py` | IT graph definition | Add nodes, change IT workflow |
| `agents/wash_trade/agent.py` | WT graph definition | Add nodes, change WT workflow |
| `models/insider_trading.py` | IT output schema | Change IT decision structure |
| `models/wash_trade.py` | WT output schema | Change WT decision structure |
| `tools/base.py` | Tool infrastructure | Common tool functionality |
| `agents/wash_trade/tools/` | WT-specific tools | Add/modify wash trade analysis |
| `reports/html_generator.py` | IT HTML report generation | Change IT report styling/layout |
| `reports/wash_trade_report.py` | WT HTML report generation | Change WT report styling/SVG |
| `config.py` | Environment config | Add config parameters |
| `main.py` | Entry point | CLI arguments, output formatting |
| `a2a/orchestrator.py` | Alert routing logic | Add new alert types or agents |
| `a2a/insider_trading_executor.py` | IT A2A executor | Modify how IT alerts are processed |
| `a2a/wash_trade_executor.py` | WT A2A executor | Modify how WT alerts are processed |
| `a2a/*_server.py` | A2A servers | Change server configuration |
| `frontend/app.py` | Web UI backend | Add API endpoints, A2A integration |
| `frontend/static/js/results.js` | Results rendering | Add UI sections, modify Cytoscape graph |
| `frontend/task_manager.py` | Task tracking | Modify task lifecycle |

## Anti-Patterns to Avoid

1. **Don't return raw data from tools** - Always use LLM to interpret first
2. **Don't add hardcoded scoring** - Use few-shot examples instead
3. **Don't silently catch errors** - Let them crash (fail-fast)
4. **Don't create new data sources** without updating architecture docs
5. **Don't modify `.env`** - It contains secrets and is gitignored
6. **Don't create files in project root** - Use `scripts/`, `test_data/`, or `resources/` subdirectories

## Reference Documentation

- LangGraph docs: `resources/research/langgraph/` (comprehensive reference materials)
- Architecture design: `.dev-resources/architecture/smarts-alert-analyzer.md`
- Wash trade architecture: `.dev-resources/architecture/wash-trade-analyzer.md`
- Architecture prompts: `.dev-resources/prompts/architecture.txt`
