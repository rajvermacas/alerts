# SMARTS Alert Analyzer - Developer Reference

**Mission**: Multi-agent LLM system analyzing SMARTS surveillance alerts (insider trading, wash trading) to reduce false positives. Pure agentic reasoning with no hardcoded scoring.

**Core Philosophy**: Behavior tuning via few-shot examples in JSON files (zero code changes required).

---

## Quick Start

### Setup
```bash
pip install -e ".[dev]"             # Install with dev dependencies
cp .env.example .env                # Configure: LLM_PROVIDER, API keys
pytest --cov=alerts                 # Run tests with coverage
```

### Run Analysis

**CLI (single alert)**:
```bash
python -m alerts.main                                      # Default IT alert
python -m alerts.main --alert test_data/alerts/wash_trade/wash_genuine.xml
```

**Multi-Agent (A2A servers + web UI)**:
```bash
bash scripts/start_all_servers.sh   # All servers in background
# Open: http://localhost:8080
# Logs: logs/{insider_trading,wash_trade,orchestrator,frontend}.log
```

---

## Architecture

### Multi-Agent Flow
```
User/Browser → Orchestrator (10000) → IT Agent (10001) / WT Agent (10002) → Decision
```

**Alert Detection**:
- IT: Keywords `insider|pre-announcement|mnpi`, rule codes `SMARTS-IT-*|SMARTS-PAT-*`
- WT: Keywords `wash|self-trade|circular`, rule codes `SMARTS-WT-*|WT-*|WASH_TRADE`

### Proactive Data Flow (AlertContext Architecture)

```
BigDataSimulator → AnalysisRequest → Agent → Tools (parallel execution)
  (mock/POC)          ↓                 ↓
Parse XML to      alert_context   Read context directly
AlertContext      (structured)    (no tool, no LLM)
                     +
                  tool_data
                (pre-aggregated)
```

**Key Components**:
- `BigDataSimulator` (POC): Parses XML → structured `AlertContext`, loads tool data
- `AnalysisRequest`: Contains `alert_context` (structured) + all tool data pre-aggregated
- `AlertContext`: Discriminated union (`InsiderTradingAlertContext` | `WashTradeAlertContext`)
- `ToolInput`: Format + data for each tool
- Tools: Receive data via `execute(data, format)` - no file loading

**Tool Architecture** (Two-Tier LLM):
1. Data injected → Tool validates format
2. Tool LLM interprets raw data → insights
3. Agent LLM reasons over insights → decision

**Common Tools** (all agents): `trader_profile`, `market_data`
**IT Tools**: `trader_history`, `market_news`
**WT Tools**: `account_relationships`, `related_accounts_history`, `trade_timing`, `counterparty_analysis`

**Note**: `AlertReaderTool` was removed - alert context is now parsed by Big Data Layer into structured `AlertContext` before reaching agents.

### Event Streaming (SSE)

```
Browser EventSource → Frontend proxy → Orchestrator → Agent → LangGraph
                                       ↓ SSE events
context_received → tool_started → tool_progress → tool_completed → analysis_complete
```

**Event Mapper**: `a2a/event_mapper.py` - LangGraph → A2A conversion
**Frontend**: `static/js/streaming.js`, `dag-visualization.js`

**Event Flow**:
1. `context_received` - Alert context loaded (replaces old `alert_reader` tool events)
2. `tool_started` - Tool execution begins (all tools run in parallel)
3. `tool_progress` - Tool processing updates
4. `tool_completed` - Tool execution finished
5. `analysis_complete` - Final decision ready

---

## Directory Structure

```
src/alerts/
├── main.py                     # CLI entry point
├── config.py                   # Env-based config (fail-fast)
├── llm_factory.py              # 4 LLM providers
├── exceptions.py               # MissingToolDataError, InvalidFormatError
├── models/
│   ├── base.py                 # BaseAlertDecision
│   ├── alert_context.py        # AlertContext models (IT/WT structured context)
│   ├── insider_trading.py      # InsiderTradingDecision (11 fields)
│   ├── wash_trade.py           # WashTradeDecision (14 fields)
│   └── request.py              # AnalysisRequest, ToolInput (proactive flow)
├── agents/
│   ├── insider_trading/
│   │   ├── agent.py            # InsiderTradingAnalyzerAgent
│   │   ├── prompts/system_prompt.py
│   │   └── tools/              # trader_history.py, market_news.py
│   └── wash_trade/
│       ├── agent.py            # WashTradeAnalyzerAgent
│       ├── prompts/system_prompt.py
│       └── tools/              # 4 WT-specific tools
├── tools/common/               # Shared tools (2 tools)
│   ├── base.py                 # BaseTool (LLM + streaming)
│   ├── trader_profile.py       # Trader MNPI access analysis
│   └── market_data.py          # Market conditions analysis
├── reports/
│   ├── html_generator.py       # IT HTML (Tailwind CSS)
│   ├── wash_trade_report.py    # WT HTML + network graph
│   └── wash_trade_graph.py     # SVG visualization
├── a2a/                        # Agent-to-Agent protocol servers
│   ├── orchestrator*.py        # Port 10000
│   ├── insider_trading*.py     # Port 10001
│   ├── wash_trade*.py          # Port 10002
│   └── event_mapper.py         # SSE event conversion
└── mock/
    └── bigdata_simulator.py    # POC: test_data → AnalysisRequest

src/frontend/
├── app.py                      # FastAPI + A2A client + SSE proxy
├── task_manager.py             # In-memory task tracking
├── templates/                  # base.html, upload.html
└── static/js/                  # streaming.js, dag-visualization.js, results.js

test_data/
├── alerts/*.xml                # IT test cases
├── alerts/wash_trade/*.xml     # WT test cases
├── few_shot_examples.json      # IT behavior tuning ← EDIT HERE
├── wash_trade_few_shot_examples.json # WT behavior tuning ← EDIT HERE
└── *.csv, market_news.txt      # Tool data sources

resources/reports/              # Output: decision_{id}.json/html, audit_log.jsonl
scripts/                        # start_all_servers.sh, test_frontend_api.sh
logs/                           # Runtime logs
```

---

## Integration Points

### LLM Providers
Set `LLM_PROVIDER` in `.env`:
- `openai`: `OPENAI_API_KEY`, `OPENAI_MODEL`
- `azure`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`
- `openrouter`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`
- `gemini`: `GOOGLE_API_KEY`, `GEMINI_MODEL`

### A2A Server URLs (Default)
- Orchestrator: `http://localhost:10000`
- IT Agent: `http://localhost:10001`
- WT Agent: `http://localhost:10002`
- Frontend: `http://localhost:8080`

Override via CLI args: `--port`, `--orchestrator-url`, `--insider-trading-url`, `--wash-trade-url`

### Frontend API Endpoints
- `POST /api/analyze` - Upload alert
- `GET /api/stream/{task_id}` - SSE progress stream
- `GET /api/status/{task_id}` - Polling fallback
- `GET /api/download/{task_id}/json|html` - Download reports

---

## Development Patterns

### Tune Agent Behavior (No Code Changes)

**Priority 1**: Edit few-shot examples (most effective)
- IT: `test_data/few_shot_examples.json`
- WT: `test_data/wash_trade_few_shot_examples.json`

**Priority 2**: Update system prompts
- IT: `agents/insider_trading/prompts/system_prompt.py`
- WT: `agents/wash_trade/prompts/system_prompt.py`

**Priority 3**: Modify agent graph (last resort)
- `agents/{it|wt}/agent.py:_build_graph()`

### Add New Tool

**Common tool** (all agents):
1. Create `tools/common/your_tool.py` inheriting `BaseTool`
2. Set `expected_format` class attribute (csv, xml, txt)
3. Implement `_build_interpretation_prompt(raw_data, **kwargs)` ONLY
4. Export in `tools/common/__init__.py`
5. Add to both agents: `_create_tool_instances()`
6. Update `REQUIRED_TOOLS_BY_AGENT` and `TOOL_FORMATS` in `models/request.py`
7. Test in `tests/test_tools.py`

**Agent-specific tool**: Same pattern in `agents/{it|wt}/tools/`

**Tool Contract**:
```python
class YourTool(BaseTool):
    expected_format: str = "csv"  # or "xml", "txt"

    def _build_interpretation_prompt(self, raw_data: str, **kwargs) -> str:
        return f"Analyze this: {raw_data}"

    # BaseTool.execute() handles: validate → LLM interpret → emit events → return
```

### Add New Agent Type
1. Create `agents/your_type/agent.py`
2. Define `models/your_type.py` extending `BaseAlertDecision`
3. Create tools in `agents/your_type/tools/`
4. Add system prompt `agents/your_type/prompts/system_prompt.py`
5. Create A2A executor/server: `a2a/your_type_executor.py`, `a2a/your_type_server.py`
6. Update orchestrator: `a2a/orchestrator.py:determine_alert_type()`, `route_to_agent()`
7. Update `models/request.py:REQUIRED_TOOLS_BY_AGENT`
8. Tests: `tests/test_a2a_orchestrator.py`

### Extend SSE Events
1. Add event type: `a2a/event_mapper.py:map_*_event()`
2. Update frontend: `frontend/static/js/progress-timeline.js:_handleEvent()`
3. Update DAG: `frontend/static/js/dag-visualization.js`

---

## Key Constraints

### Fail-Fast Philosophy
**No graceful degradation**. Errors crash loudly.
- Tool failure → analysis fails
- Missing env var → startup fails
- Invalid data format → exception raised

Rationale: POC phase prioritizes visibility over resilience.

### No Hardcoded Scoring
**Pure LLM reasoning**. Zero formulas.
- Tune via few-shot examples, not code
- No `if confidence > 0.7` logic
- No threshold constants

### Tool Returns Insights, Not Data
**Two-tier LLM approach**:
- Tool LLM: Interprets raw data → insights
- Agent LLM: Reasons over insights → decision

❌ Bad: `"trader_history.csv has 247 rows"`
✅ Good: `"Trader typically 5K shares/day tech. Flagged 50K healthcare = 10x volume, new sector"`

### Proactive Information Flow
**Data is injected, not pulled**:
- Big Data Layer aggregates all tool data
- Packages into `AnalysisRequest`
- Sends to orchestrator/agent
- Tools receive via `execute(data=..., format=...)`
- Tools NEVER load files directly

Production transition: Replace `BigDataSimulator` with real DB/API client. Tool code unchanged.

---

## Output Formats

**Decision Files**:
- JSON: `resources/reports/decision_{alert_id}.json`
- HTML: `resources/reports/decision_{alert_id}.html` (Tailwind CSS)
- Audit: `resources/reports/audit_log.jsonl` (append-only)

**IT Decision Schema (11 fields)**: `determination`, `genuine_alert_confidence`, `false_positive_confidence`, `key_findings`, `favorable_indicators`, `risk_mitigating_factors`, `trader_baseline_analysis`, `market_context`, `reasoning_narrative`, `similar_precedent`, `recommended_action`

**WT Decision Schema (14 fields)**: IT fields + `relationship_network`, `timing_patterns`, `trade_flows`, `counterparty_patterns`

---

## Anti-Patterns

❌ Return raw data from tools
❌ Add hardcoded scoring/thresholds
❌ Silently catch errors
❌ Modify `.env` file
❌ Tools loading their own data files
❌ Create files in project root

---

## Reference

**LangGraph**: `resources/research/langgraph/`
**Architecture**: `.dev-resources/architecture/*.md`
**A2A Protocol**: Google's Agent-to-Agent standard (JSON-RPC over HTTP)
