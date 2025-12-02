---
name: a2a-protocol
description: Guide for implementing A2A (Agent-to-Agent) Protocol for multi-agent communication and orchestration. Use when planning or implementing multi-agent systems, evaluating whether to adopt A2A vs staying with monolithic agents, integrating external specialist agents, implementing agent discovery and routing, or working with LangGraph/LangChain multi-agent architectures. Also use for understanding A2A security patterns (OAuth 2.0, JWT, mTLS) and production deployment strategies.
---

# A2A Protocol Implementation Guide

## Overview

The Agent-to-Agent (A2A) Protocol is an open standard for enabling AI agents from different frameworks and organizations to communicate seamlessly. Backed by 150+ organizations including Google, Microsoft, Amazon, and Salesforce.

**Key principle**: A2A solves the problem of multi-agent interoperability. Use it when you need agents to collaborate as equals, not when wrapping agents as tools.

## When to Use A2A

### Use A2A When:
- Building ecosystem of multiple specialized agents
- Multiple teams building agents that must collaborate
- Integrating third-party specialist agents
- Need external agent integration (different orgs/teams)
- Scaling beyond single agent's capacity
- Regulatory requirements demand separate system audit trails

### Don't Use A2A When:
- Single monolithic agent is sufficient for your use case
- Team is small and co-located
- Performance is critical (multi-agent adds latency overhead)
- All functionality can be handled by tools within one agent
- Complexity budget is exhausted

## A2A vs MCP (Complementary)

| Aspect | A2A | MCP |
|--------|-----|-----|
| **Solves** | Agent-to-Agent communication | Agent-to-Tool communication |
| **Use Case** | Multi-agent workflows | Single agent, multiple tools |
| **Interaction** | Bidirectional negotiation | Client → Server calls |
| **Discovery** | Agent Cards, registries | Server manifest |

**Best Practice**: Use both together - MCP for tools, A2A for agent collaboration.

## Quick Start

### 1. Expose Your Agent via A2A

```python
from fastapi import FastAPI, Header

app = FastAPI()

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    """A2A Agent Card for discovery"""
    return {
        "id": "agent/your-agent/v1",
        "name": "Your Agent Name",
        "description": "What your agent does",
        "endpoint": "https://api.example.com/a2a",
        "version": "1.0.0",
        "skills": [
            {
                "id": "main_skill",
                "name": "Main Skill",
                "description": "Primary capability",
                "inputs": ["text_input"],
                "outputs": ["result"]
            }
        ]
    }

@app.post("/a2a/message/send")
async def send_message(request: dict, x_api_key: str = Header(...)):
    """Handle incoming A2A messages"""
    message = request["params"]["message"]
    user_text = message["parts"][0]["text"]

    # Process with your agent
    result = await your_agent.process(user_text)

    return {
        "jsonrpc": "2.0",
        "result": {
            "artifacts": [{
                "id": "art_1",
                "parts": [{"kind": "text", "text": result}]
            }]
        }
    }
```

### 2. Call Other Agents

```python
import httpx

async def call_specialist_agent(text: str):
    """Call external specialist agent via A2A"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://specialist-agent.com/a2a/message/send",
            json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": text}]
                    }
                }
            },
            headers={"x-api-key": "your-api-key"}
        )
        return response.json()["result"]
```

## LangGraph Integration

**Good news**: LangGraph automatically provides A2A support when deployed to LangGraph Platform.

```python
# Your existing LangGraph agent works as-is
from langgraph.graph import StateGraph, MessagesState

workflow = StateGraph(MessagesState)
workflow.add_node("agent", agent_node)
workflow.add_edge("agent", END)

app = workflow.compile()

# Deploy to LangGraph Platform
# langgraph deploy

# Automatically provides:
# - POST /a2a/{assistant_id}/message/send
# - GET /.well-known/agent-card.json
```

## Reference Documentation

For detailed implementation guidance, see the references directory:

- **[decision-framework.md](references/decision-framework.md)** - When to adopt A2A vs alternatives, architecture assessment, migration paths
- **[implementation-patterns.md](references/implementation-patterns.md)** - Production-ready code templates with error handling, retry logic, and best practices
- **[security-guide.md](references/security-guide.md)** - OAuth 2.0, JWT, mTLS patterns, enterprise security requirements
- **[integration-guide.md](references/integration-guide.md)** - LangGraph/LangChain integration, multi-agent orchestration patterns

## Common Patterns

### Pattern 1: Agent Discovery

```python
async def discover_agent(endpoint: str):
    """Discover agent capabilities"""
    async with httpx.AsyncClient() as client:
        card = await client.get(f"{endpoint}/.well-known/agent-card.json")
        return card.json()

# Use discovered capabilities
agent_card = await discover_agent("https://api.example.com")
print(f"Agent skills: {agent_card['skills']}")
```

### Pattern 2: Multi-Agent Orchestration

```python
async def orchestrate_analysis(data: dict):
    """Coordinate multiple specialist agents"""

    # Call specialists in parallel
    compliance_task = call_agent("compliance-agent", data)
    risk_task = call_agent("risk-agent", data)

    compliance, risk = await asyncio.gather(compliance_task, risk_task)

    # Aggregate results
    return aggregate_results(compliance, risk)
```

### Pattern 3: Circuit Breaker for Resilience

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def call_external_agent(endpoint: str, message: str):
    """Call with automatic circuit breaking"""
    # Fails fast if agent is down
    return await a2a_client.send_message(message)
```

## Production Checklist

Before deploying A2A agents to production:

**Security**:
- [ ] Implement OAuth 2.0 or API key authentication
- [ ] Use HTTPS/TLS 1.3+ for all communication
- [ ] Validate webhook URLs (prevent SSRF)
- [ ] Set token expiration < 15 minutes
- [ ] Implement rate limiting

**Reliability**:
- [ ] Add retry logic with exponential backoff
- [ ] Implement circuit breakers for failing agents
- [ ] Set appropriate timeouts (30s recommended)
- [ ] Monitor agent availability

**Observability**:
- [ ] Log all inter-agent communications
- [ ] Track latency and error rates
- [ ] Implement distributed tracing
- [ ] Set up alerting for agent failures

## Migration from Monolithic Agent

If transitioning from a single agent to multi-agent:

1. **Keep existing agent intact** - Don't break what works
2. **Extract one specialist** - Start with clearest separation
3. **Expose via A2A** - Add agent card and endpoints
4. **Test integration** - Verify communication works
5. **Iterate** - Extract more specialists as needed

**Timeline**: 2-4 weeks for first specialist integration (experienced team)

## Real-World Examples

- **Tyson Foods**: Supply chain agent collaboration
- **Adobe**: Cross-ecosystem workflow automation
- **S&P Global**: Market intelligence agent interoperability
- **Renault**: EV infrastructure optimization

## Key Resources

- A2A Specification: https://a2a-protocol.org/latest/specification/
- LangGraph A2A Documentation: https://docs.langchain.com/langgraph-platform/server-a2a
- Google A2A Announcement: https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- Comprehensive research: `/resources/research/a2a-protocol/` (61 sources analyzed)

## Getting Help

1. Check [decision-framework.md](references/decision-framework.md) for architecture decisions
2. Review [implementation-patterns.md](references/implementation-patterns.md) for code examples
3. Consult [security-guide.md](references/security-guide.md) for enterprise deployment
4. See comprehensive research documents in `/resources/research/a2a-protocol/`
