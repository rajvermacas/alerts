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
# Option 1: Use helper script to start all servers in background
bash scripts/start_all_servers.sh
# Logs: logs/insider_trading.log, logs/wash_trade.log, logs/orchestrator.log, logs/frontend.log
# Open browser: http://localhost:8080

# Option 2: Start all required servers manually (4 terminals)

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
- **Insider Trading Agent**: 3 common tools + 3 IT-specific tools (6 total)
- **Wash Trade Agent**: 3 common tools + 4 WT-specific tools (7 total)

Each tool:
1. Reads from a data source (CSV/XML/TXT files in POC)
2. **Calls LLM internally** to interpret raw data
3. Returns **insights** (not raw data) to the main agent

This creates a **two-tier LLM architecture**:
- **Tier 1**: Tool-level LLMs extract insights from raw data
- **Tier 2**: Main agent LLM makes final determination using tool insights + few-shot examples

### Core Components

The codebase is organized into **Backend** (analysis engine) and **Frontend** (web UI):

#### Backend (`src/alerts/`)
```
src/alerts/
├── main.py                      # CLI entry point
├── config.py                    # Environment-based configuration
├── llm_factory.py               # LLM provider factory (OpenAI/Azure/OpenRouter/Gemini)
├── agent.py                     # [Backward-compat shim → agents.insider_trading]
├── models.py                    # [Backward-compat shim → models/]
├── models/
│   ├── base.py                  # BaseAlertDecision
│   ├── insider_trading.py       # InsiderTradingDecision
│   └── wash_trade.py            # WashTradeDecision + RelationshipNetwork
├── prompts/                     # [Backward-compat shim → agents.insider_trading.prompts]
│   └── system_prompt.py
├── tools/
│   ├── base.py                  # BaseTool class with LLM interpretation + streaming
│   ├── common/                  # 3 shared tools (used by ALL agents)
│   │   ├── alert_reader.py      # AlertReaderTool - parses alert XML
│   │   ├── trader_profile.py    # TraderProfileTool - role/access level
│   │   └── market_data.py       # MarketDataTool - price/volume data
│   └── [legacy files]           # Old implementations (use common/ instead)
├── agents/
│   ├── insider_trading/
│   │   ├── agent.py             # InsiderTradingAnalyzerAgent
│   │   ├── prompts/
│   │   │   └── system_prompt.py
│   │   └── tools/               # 3 insider-trading-specific tools
│   │       ├── trader_history.py    # TraderHistoryTool
│   │       ├── market_news.py       # MarketNewsTool
│   │       └── peer_trades.py       # PeerTradesTool
│   └── wash_trade/
│       ├── agent.py             # WashTradeAnalyzerAgent
│       ├── prompts/
│       │   └── system_prompt.py
│       └── tools/               # 4 wash-trade-specific tools
│           ├── account_relationships.py
│           ├── related_accounts_history.py
│           ├── trade_timing.py
│           └── counterparty_analysis.py
├── reports/
│   ├── html_generator.py        # Insider trading HTML report
│   ├── wash_trade_report.py     # Wash trade HTML report
│   └── wash_trade_graph.py      # SVG network graph generator
└── a2a/                         # A2A (Agent-to-Agent) protocol integration
    ├── event_mapper.py          # LangGraph → A2A event format conversion
    ├── insider_trading_executor.py  # execute() + execute_stream()
    ├── insider_trading_server.py    # /message/stream SSE endpoint
    ├── wash_trade_executor.py
    ├── wash_trade_server.py
    ├── orchestrator.py          # Routes alerts to specialized agents
    ├── orchestrator_executor.py # Proxies streaming from agents
    ├── orchestrator_server.py
    └── test_client.py
```

#### Frontend (`src/frontend/`)
```
src/frontend/
├── app.py                       # FastAPI routes, A2A client, SSE proxy
├── task_manager.py              # In-memory task tracking (POC)
├── templates/
│   ├── base.html                # Tailwind CSS base template
│   └── upload.html              # Upload page with timeline UI
└── static/
    ├── css/styles.css           # Custom animations, timeline styles
    └── js/
        ├── upload.js            # Drag-drop file upload
        ├── progress-timeline.js # SSE timeline visualization
        ├── streaming.js         # EventSource integration (fail-fast)
        └── results.js           # Results + Cytoscape.js network graph
```

#### Supporting Directories
```
test_data/                       # Test fixtures
├── alerts/                      # Insider trading alert XMLs
│   └── wash_trade/              # Wash trade alert XMLs
├── wash_trade/                  # Wash trade CSV data files
├── *.csv                        # Market/trader data
├── few_shot_examples.json       # Insider trading precedents
└── wash_trade_few_shot_examples.json  # Wash trade precedents

tests/                           # pytest test suite
resources/
├── reports/                     # Output directory for decisions
├── debug/                       # Debug dumps (A2A responses)
└── research/                    # Reference documentation (LangGraph, A2A)
scripts/                         # Utility scripts
logs/                            # Runtime logs
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

# Test with insider trading alerts
python -m alerts.a2a.test_client --server-url http://localhost:10000 \
    --alert test_data/alerts/alert_genuine.xml

# Test with wash trade alerts
python -m alerts.a2a.test_client --server-url http://localhost:10000 \
    --alert test_data/alerts/wash_trade/wash_genuine.xml
python -m alerts.a2a.test_client --server-url http://localhost:10000 \
    --alert test_data/alerts/wash_trade/wash_ambiguous.xml
python -m alerts.a2a.test_client --server-url http://localhost:10000 \
    --alert test_data/alerts/wash_trade/wash_layered.xml
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

**Environment-based** configuration supporting OpenAI, Azure OpenAI, OpenRouter, and Google Gemini:

```python
# config.py uses dataclasses with fail-fast validation
AppConfig
├── LLMConfig       # Provider, model, API keys, temperature
├── DataConfig      # Paths to data_dir, output_dir, alerts
└── LoggingConfig   # Log level, format, optional file
```

Load with: `get_config()` (reads from `.env` file via `python-dotenv`)

**Provider switching**: Set `LLM_PROVIDER=openai`, `LLM_PROVIDER=azure`, `LLM_PROVIDER=openrouter`, or `LLM_PROVIDER=gemini` in `.env`

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

Code is **provider-agnostic**. Switch between four providers via configuration:

**OpenAI**:
- Environment variables: `OPENAI_API_KEY` + `OPENAI_MODEL`
- Models: Any OpenAI model (e.g., "gpt-4o", "gpt-4-turbo")

**Azure OpenAI**:
- Environment variables: `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` + `AZURE_OPENAI_API_VERSION`
- Models: Any deployed model in Azure

**OpenRouter**:
- Environment variables: `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`
- Optional: `OPENROUTER_SITE_URL` + `OPENROUTER_SITE_NAME` (for site ranking)
- Models: Any model in OpenRouter catalog (e.g., "openai/gpt-4o", "anthropic/claude-opus", "meta-llama/llama-3-8b")
- Base URL: Automatically set to `https://openrouter.ai/api/v1`

**Google Gemini**:
- Environment variables: `GOOGLE_API_KEY` + `GEMINI_MODEL`
- Models: Any Gemini model (e.g., "gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash")
- Documentation: https://ai.google.dev/gemini-api/docs

Implementation: `llm_factory.py:create_llm()` uses LangChain's `ChatOpenAI`, `AzureChatOpenAI`, or `ChatGoogleGenerativeAI`.

**Example OpenRouter Usage**:
```bash
export LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY=sk-or-...
export OPENROUTER_MODEL=anthropic/claude-opus  # Or any other model
python -m alerts.main
```

**Example Gemini Usage**:
```bash
export LLM_PROVIDER=gemini
export GOOGLE_API_KEY=your-google-api-key
export GEMINI_MODEL=gemini-2.0-flash  # Or any other Gemini model
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

**Common tools** (shared by ALL agents):
1. Create tool class in `src/alerts/tools/common/your_tool.py`
2. Inherit from `BaseTool` (from `alerts.tools.common.base`)
3. Implement `_load_data()` and `_build_interpretation_prompt()`
4. Export from `src/alerts/tools/common/__init__.py`
5. Add to EACH agent's `_create_tool_instances()` method
6. Update tests in `tests/test_tools.py`

**Agent-specific tools** (e.g., insider trading or wash trade):
1. Create tool class in `src/alerts/agents/{agent_type}/tools/your_tool.py`
2. Inherit from `BaseTool`
3. Implement `_load_data()` and `_build_interpretation_prompt()`
4. Export from `src/alerts/agents/{agent_type}/tools/__init__.py`
5. Add to the specific agent's `_create_tool_instances()` method
6. Update tests in `tests/test_tools.py`

### Modifying Agent Behavior
1. **First choice**: Edit the appropriate few-shot examples JSON file (no code changes)
2. **If insufficient**: Update system prompt in the agent's `prompts/system_prompt.py`
3. **Last resort**: Modify agent graph in the agent's `agent.py:_build_graph()`

### Testing Strategy
- Unit tests for tools, models, config, HTML generation
- Mock LLM responses for deterministic tests
- Use `conftest.py` for shared fixtures
- Test data generation scripts go in `scripts/` folder
- HTML report tests verify Tailwind CSS output and structure

**Available Helper Scripts** (`scripts/` directory):
- `start_all_servers.sh`: Starts all A2A servers and frontend in background with logging
- `test_frontend_api.sh`: Tests frontend API with insider trading alert upload and polling

### Web UI Frontend

The system includes a web interface for uploading alerts and viewing results with **real-time streaming progress**:

**Architecture:**
```
Browser (http://localhost:8080)
    │
    ├── POST /api/analyze (multipart XML upload)
    ├── GET /api/stream/{task_id} (SSE real-time streaming)
    ├── GET /api/status/{task_id} (polling fallback)
    └── GET /api/download/{task_id}/{json|html}
    │
    ▼
FastAPI Frontend Service (Port 8080)
    │
    └── POST /message/stream (A2A SSE streaming)
    │
    ▼
Orchestrator Agent (Port 10000)
    │
    └── POST /message/stream (proxies to specialized agents)
    │
    ├── Insider Trading Agent (Port 10001)
    │   └── POST /message/stream (SSE from LangGraph)
    │
    └── Wash Trade Agent (Port 10002)
        └── POST /message/stream (SSE from LangGraph)
```

**Real-Time Streaming Architecture:**

The system uses Server-Sent Events (SSE) to stream progress updates in real-time over 5-10 minute analysis tasks:

1. **Browser → Frontend**: Uses `EventSource` API to connect to `/api/stream/{task_id}`
2. **Frontend → Orchestrator**: Proxies SSE stream via `httpx.stream()` to `/message/stream`
3. **Orchestrator → Agents**: Routes stream request to appropriate agent's `/message/stream`
4. **Agent → LangGraph**: Uses `graph.astream_events()` to get tool-level progress
5. **Tool Events**: Each tool emits `tool_started`, `tool_progress`, `tool_completed` events

**Event Types:**
- `analysis_started`: Analysis begins, alert type detected
- `routing`: Orchestrator routing to specialized agent
- `tool_started`: Tool execution begins (with tool name)
- `tool_progress`: Tool processing insight (optional)
- `tool_completed`: Tool finished with insight summary
- `analysis_complete`: Final decision with determination
- `error`: Error occurred at any stage

**Key Frontend Components:**
- `frontend/app.py`: FastAPI routes, A2A client, SSE proxy endpoint
- `frontend/task_manager.py`: In-memory task tracking (POC - no persistence)
- `frontend/static/js/progress-timeline.js`: ProgressTimeline class for SSE visualization
- `frontend/static/js/streaming.js`: EventSource integration (fail-fast, no polling fallback)
- `frontend/static/js/results.js`: Dynamic rendering + Cytoscape.js graph for wash trade

**A2A Response Parsing Challenge:**
The orchestrator wraps agent responses, creating nested JSON-RPC structures. The `extract_decision_from_response()` function handles this by:
1. Detecting nested responses in artifact text
2. Extracting embedded JSON-RPC using brace matching
3. Finding artifacts ending in `_json` (e.g., `alert_decision_json`)

Debug files are saved to `resources/debug/a2a_response_*.json` for investigation.

### Real-Time Event Streaming

The streaming system provides real-time visibility into the multi-agent analysis pipeline:

**Event Format (A2A TaskStatusUpdateEvent):**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "task": {"id": "task-uuid", "state": "working"},
    "taskStatusUpdateEvent": {
      "task": {"id": "task-uuid", "state": "working"},
      "final": false
    },
    "metadata": {
      "event_id": "event-uuid",
      "event_type": "tool_completed",
      "agent": "insider_trading",
      "tool_name": "trader_history",
      "payload": {
        "message": "Trader shows unusual volume deviation",
        "stage": "data_gathering"
      }
    }
  }
}
```

**Stream Writer Pattern:**
Tools emit events via optional `stream_writer` callback:
```python
# In BaseTool.__call__()
self._emit_event(stream_writer, "tool_started", {"stage": "loading_data"})
# ... do work ...
self._emit_event(stream_writer, "tool_completed", {"insight": summary})
```

**LangGraph Integration:**
Agents use `graph.astream_events()` to capture internal LangGraph events:
```python
async for event in self.graph.astream_events(input, version="v2"):
    # Map LangGraph events to A2A format
    yield event_mapper.map_tool_event(event)
```

**Reconnection Support:**
- SSE events include `id` field for reconnection
- `EventBuffer` class (event_mapper.py) stores recent events
- Client can reconnect with `Last-Event-ID` header

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

All paths relative to `src/` unless otherwise noted.

| File | Purpose | When to Modify |
|------|---------|----------------|
| **Behavior Tuning (No Code Changes)** | | |
| `test_data/few_shot_examples.json` | IT few-shot precedents | Adjust IT agent decisions |
| `test_data/wash_trade_few_shot_examples.json` | WT few-shot precedents | Adjust WT agent decisions |
| **Backend - Agents** | | |
| `alerts/agents/insider_trading/agent.py` | IT LangGraph workflow | Add nodes, change IT workflow |
| `alerts/agents/insider_trading/prompts/system_prompt.py` | IT system prompt | Change IT reasoning approach |
| `alerts/agents/wash_trade/agent.py` | WT LangGraph workflow | Add nodes, change WT workflow |
| `alerts/agents/wash_trade/prompts/system_prompt.py` | WT system prompt | Change WT reasoning approach |
| **Backend - Tools** | | |
| `alerts/tools/base.py` | BaseTool class + streaming | Tool infrastructure changes |
| `alerts/tools/common/` | 3 shared tools | Common tool modifications |
| `alerts/agents/insider_trading/tools/` | 3 IT-specific tools | IT tool changes |
| `alerts/agents/wash_trade/tools/` | 4 WT-specific tools | WT tool changes |
| **Backend - Models** | | |
| `alerts/models/insider_trading.py` | IT output schema | Change IT decision structure |
| `alerts/models/wash_trade.py` | WT output schema | Change WT decision structure |
| **Backend - Reports** | | |
| `alerts/reports/html_generator.py` | IT HTML report | Change IT report styling |
| `alerts/reports/wash_trade_report.py` | WT HTML report | Change WT report styling |
| `alerts/reports/wash_trade_graph.py` | SVG network graph | Change network visualization |
| **Backend - A2A** | | |
| `alerts/a2a/orchestrator.py` | Alert routing logic | Add new alert types/agents |
| `alerts/a2a/event_mapper.py` | Event format conversion | Add new event types |
| `alerts/a2a/*_executor.py` | Agent executors | Modify streaming behavior |
| `alerts/a2a/*_server.py` | A2A HTTP servers | Server configuration |
| **Backend - Core** | | |
| `alerts/config.py` | Environment config | Add config parameters |
| `alerts/llm_factory.py` | LLM provider factory | Add new LLM providers |
| `alerts/main.py` | CLI entry point | CLI arguments, output |
| **Frontend** | | |
| `frontend/app.py` | FastAPI routes + SSE proxy | Add endpoints, modify streaming |
| `frontend/task_manager.py` | Task lifecycle | Modify task tracking |
| `frontend/static/js/streaming.js` | EventSource integration | SSE connection handling |
| `frontend/static/js/progress-timeline.js` | Timeline visualization | Progress UI changes |
| `frontend/static/js/results.js` | Results rendering | Result UI, Cytoscape graph |

## Anti-Patterns to Avoid

1. **Don't return raw data from tools** - Always use LLM to interpret first
2. **Don't add hardcoded scoring** - Use few-shot examples instead
3. **Don't silently catch errors** - Let them crash (fail-fast)
4. **Don't create new data sources** without updating architecture docs
5. **Don't modify `.env`** - It contains secrets and is gitignored
6. **Don't create files in project root** - Use `scripts/`, `test_data/`, or `resources/` subdirectories

## Known Issues

### BaseTool Duplication
There are currently TWO BaseTool implementations:
- `alerts/tools/base.py` (426 lines) - **NEWER** with streaming support via `_emit_event()`, updated Dec 3 20:38
- `alerts/tools/common/base.py` (332 lines) - **OLDER** without streaming, updated Dec 3 09:44

**Current State**: All tools import from the older `alerts.tools.common.base` which lacks streaming support. The newer `alerts/tools/base.py` with streaming is not being used.

**Impact**: Tools do not emit real-time progress events despite the streaming infrastructure being in place.

**Resolution Needed**: Either:
1. Update `alerts/tools/common/base.py` with streaming support from `alerts/tools/base.py`
2. Change all tool imports to use `alerts.tools.base` instead of `alerts.tools.common.base`
3. Make `alerts/tools/common/base.py` re-export from `alerts.tools.base`

## Reference Documentation

- LangGraph docs: `resources/research/langgraph/` (comprehensive reference materials)
- Architecture design: `.dev-resources/architecture/smarts-alert-analyzer.md`
- Wash trade architecture: `.dev-resources/architecture/wash-trade-analyzer.md`
- Agent event streaming: `.dev-resources/architecture/agent-event-streaming.md`
- UI architecture: `.dev-resources/architecture/ui-architecture.md`
- Architecture prompts: `.dev-resources/prompts/architecture.txt`
