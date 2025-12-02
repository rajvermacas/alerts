# A2A Protocol: Integration Guide

## Table of Contents
1. [LangGraph Integration](#langgraph-integration)
2. [LangChain Integration](#langchain-integration)
3. [Multi-Agent Orchestration](#multi-agent-orchestration)
4. [Deployment Strategies](#deployment-strategies)

## LangGraph Integration

### Auto-A2A Support (LangGraph Platform)

**Good news**: LangGraph Platform provides automatic A2A support. No code changes needed.

```python
from langgraph.graph import StateGraph, MessagesState, START, END

# Your existing LangGraph agent
workflow = StateGraph(MessagesState)
workflow.add_node("agent", agent_node)
workflow.add_edge(START, "agent")
workflow.add_edge("agent", END)

app = workflow.compile()

# Deploy to LangGraph Platform
# $ langgraph deploy

# Automatically provides:
# - POST /a2a/{assistant_id}/message/send
# - POST /a2a/{assistant_id}/message/stream
# - GET /.well-known/agent-card.json?assistant_id={assistant_id}
```

**Requirements**:
1. State must have `messages` key (LangGraph MessagesState provides this)
2. Messages must follow standard format: `{"role": str, "content": str}`

### Manual A2A Integration (Self-Hosted)

If not using LangGraph Platform, add A2A endpoints manually:

```python
from fastapi import FastAPI
from langgraph.graph import StateGraph, MessagesState
from typing import List, TypedDict

app = FastAPI()

# Your LangGraph agent
workflow = StateGraph(MessagesState)
# ... add nodes, edges ...
graph = workflow.compile()

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    """Expose agent capabilities"""
    return {
        "id": "agent/my-agent/v1",
        "name": "My LangGraph Agent",
        "description": "Analyzes data using LangGraph",
        "endpoint": "https://api.example.com/a2a",
        "version": "1.0.0",
        "capabilities": {
            "streaming": True,  # LangGraph supports streaming
            "pushNotifications": False,
            "longRunningOperations": False
        },
        "skills": [
            {
                "id": "analyze",
                "name": "Analyze Data",
                "description": "Performs data analysis",
                "inputs": ["data"],
                "outputs": ["insights"]
            }
        ]
    }

@app.post("/a2a/message/send")
async def send_message(request: dict):
    """Handle A2A message/send"""

    # Extract A2A message
    a2a_message = request["params"]["message"]

    # Convert to LangGraph format
    langgraph_state = {
        "messages": [
            {
                "role": part.get("role", "user"),
                "content": part["text"]
            }
            for part in a2a_message["parts"]
            if part.get("kind") == "text"
        ]
    }

    # Invoke LangGraph agent
    result = await graph.ainvoke(langgraph_state)

    # Convert LangGraph output to A2A format
    assistant_message = result["messages"][-1]["content"]

    return {
        "jsonrpc": "2.0",
        "result": {
            "artifacts": [
                {
                    "id": "art_1",
                    "parts": [
                        {"kind": "text", "text": assistant_message}
                    ]
                }
            ]
        }
    }
```

### Calling Other A2A Agents from LangGraph

```python
from typing import Annotated
from langchain_core.tools import tool
import httpx

@tool
async def call_specialist_agent(query: str) -> str:
    """Call external specialist agent via A2A"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://specialist.example.com/a2a/message/send",
            json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": query}]
                    }
                }
            },
            headers={"x-api-key": "your-key"}
        )

        result = response.json()
        return result["result"]["artifacts"][0]["parts"][0]["text"]

# Add tool to LangGraph agent
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
tools = [call_specialist_agent]

agent = create_react_agent(llm, tools)
```

## LangChain Integration

### Using LangChain with A2A

LangChain doesn't have native A2A support, but integration is straightforward:

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain.tools import Tool
import httpx

# Create A2A client tool
async def call_a2a_agent(query: str) -> str:
    """Call A2A agent from LangChain"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            os.getenv("A2A_AGENT_ENDPOINT"),
            json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": query}]
                    }
                }
            },
            headers={"x-api-key": os.getenv("A2A_API_KEY")}
        )
        result = response.json()
        return result["result"]["artifacts"][0]["parts"][0]["text"]

# Wrap as LangChain tool
a2a_tool = Tool(
    name="specialist_agent",
    func=call_a2a_agent,
    description="Call specialist agent for complex analysis"
)

# Use in agent
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
tools = [a2a_tool]
agent = create_react_agent(llm, tools)
agent_executor = AgentExecutor(agent=agent, tools=tools)
```

### Exposing LangChain Agent as A2A Service

```python
from fastapi import FastAPI
from langchain.agents import AgentExecutor
from langchain_anthropic import ChatAnthropic

app = FastAPI()

# Your LangChain agent
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
tools = [...]  # Your tools
agent_executor = AgentExecutor(agent=create_react_agent(llm, tools), tools=tools)

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return {
        "id": "agent/langchain-agent/v1",
        "name": "LangChain Agent",
        "endpoint": "https://api.example.com/a2a",
        "skills": [...]
    }

@app.post("/a2a/message/send")
async def send_message(request: dict):
    # Extract message
    a2a_message = request["params"]["message"]
    user_text = a2a_message["parts"][0]["text"]

    # Invoke LangChain agent
    result = await agent_executor.ainvoke({"input": user_text})

    # Return A2A response
    return {
        "jsonrpc": "2.0",
        "result": {
            "artifacts": [
                {
                    "id": "art_1",
                    "parts": [{"kind": "text", "text": result["output"]}]
                }
            ]
        }
    }
```

## Multi-Agent Orchestration

### Pattern 1: Sequential Workflow

Agents called one after another, each building on previous results.

```python
async def sequential_workflow(data: dict):
    """Call agents in sequence"""

    # Step 1: Data extraction agent
    extraction_client = A2AClient(
        endpoint="https://extraction-agent.com/a2a",
        api_key=os.getenv("EXTRACTION_KEY")
    )
    extracted = await extraction_client.send_message(
        "Extract key information",
        extra_data=data
    )

    # Step 2: Analysis agent (uses extracted data)
    analysis_client = A2AClient(
        endpoint="https://analysis-agent.com/a2a",
        api_key=os.getenv("ANALYSIS_KEY")
    )
    analyzed = await analysis_client.send_message(
        "Analyze extracted data",
        extra_data=extracted
    )

    # Step 3: Recommendation agent (uses analysis)
    recommendation_client = A2AClient(
        endpoint="https://recommendation-agent.com/a2a",
        api_key=os.getenv("RECOMMENDATION_KEY")
    )
    recommendation = await recommendation_client.send_message(
        "Provide recommendation",
        extra_data=analyzed
    )

    return recommendation
```

### Pattern 2: Parallel Execution

Independent agents called simultaneously, results aggregated.

```python
import asyncio

async def parallel_workflow(data: dict):
    """Call agents in parallel"""

    # Define independent tasks
    async def get_compliance():
        client = A2AClient(
            endpoint="https://compliance-agent.com/a2a",
            api_key=os.getenv("COMPLIANCE_KEY")
        )
        return await client.send_message("Check compliance", extra_data=data)

    async def get_risk():
        client = A2AClient(
            endpoint="https://risk-agent.com/a2a",
            api_key=os.getenv("RISK_KEY")
        )
        return await client.send_message("Assess risk", extra_data=data)

    async def get_sentiment():
        client = A2AClient(
            endpoint="https://sentiment-agent.com/a2a",
            api_key=os.getenv("SENTIMENT_KEY")
        )
        return await client.send_message("Analyze sentiment", extra_data=data)

    # Execute in parallel
    compliance, risk, sentiment = await asyncio.gather(
        get_compliance(),
        get_risk(),
        get_sentiment()
    )

    # Aggregate results
    return {
        "compliance": compliance,
        "risk": risk,
        "sentiment": sentiment,
        "final_score": calculate_score(compliance, risk, sentiment)
    }
```

### Pattern 3: Dynamic Routing

Route to appropriate specialist based on input classification.

```python
async def dynamic_routing(query: str, data: dict):
    """Route to appropriate specialist agent"""

    # Classify the query
    classifier_client = A2AClient(
        endpoint="https://classifier-agent.com/a2a",
        api_key=os.getenv("CLASSIFIER_KEY")
    )
    classification = await classifier_client.send_message(
        f"Classify this query: {query}"
    )

    # Route based on classification
    if "legal" in classification.lower():
        specialist_endpoint = "https://legal-agent.com/a2a"
        specialist_key = os.getenv("LEGAL_KEY")
    elif "financial" in classification.lower():
        specialist_endpoint = "https://financial-agent.com/a2a"
        specialist_key = os.getenv("FINANCIAL_KEY")
    else:
        specialist_endpoint = "https://general-agent.com/a2a"
        specialist_key = os.getenv("GENERAL_KEY")

    # Call appropriate specialist
    specialist_client = A2AClient(
        endpoint=specialist_endpoint,
        api_key=specialist_key
    )
    return await specialist_client.send_message(query, extra_data=data)
```

### Pattern 4: Hierarchical Delegation

Main orchestrator delegates to sub-orchestrators.

```python
async def hierarchical_orchestration(task: dict):
    """
    Main Orchestrator
        ├─ Regional Orchestrator (US)
        │   ├─ State Agent (CA)
        │   └─ State Agent (NY)
        └─ Regional Orchestrator (EU)
            ├─ Country Agent (DE)
            └─ Country Agent (FR)
    """

    region = task.get("region")

    if region == "US":
        orchestrator_endpoint = "https://us-orchestrator.com/a2a"
    elif region == "EU":
        orchestrator_endpoint = "https://eu-orchestrator.com/a2a"
    else:
        raise ValueError(f"Unknown region: {region}")

    # Delegate to regional orchestrator
    regional_client = A2AClient(
        endpoint=orchestrator_endpoint,
        api_key=os.getenv("REGIONAL_KEY")
    )

    return await regional_client.send_message(
        "Handle regional task",
        extra_data=task
    )
```

## Deployment Strategies

### Strategy 1: Containerized Deployment (Docker)

```dockerfile
# Dockerfile for A2A agent
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose A2A endpoint
EXPOSE 8000

CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml for multi-agent system
version: '3.8'

services:
  orchestrator:
    build: ./orchestrator
    ports:
      - "8000:8000"
    environment:
      - COMPLIANCE_AGENT_URL=http://compliance:8001/a2a
      - RISK_AGENT_URL=http://risk:8002/a2a

  compliance:
    build: ./compliance-agent
    ports:
      - "8001:8001"

  risk:
    build: ./risk-agent
    ports:
      - "8002:8002"
```

### Strategy 2: Kubernetes Deployment

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: compliance-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: compliance-agent
  template:
    metadata:
      labels:
        app: compliance-agent
    spec:
      containers:
      - name: agent
        image: your-registry/compliance-agent:latest
        ports:
        - containerPort: 8000
        env:
        - name: AGENT_API_KEY
          valueFrom:
            secretKeyRef:
              name: agent-secrets
              key: api-key
---
apiVersion: v1
kind: Service
metadata:
  name: compliance-agent
spec:
  selector:
    app: compliance-agent
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Strategy 3: Serverless (AWS Lambda)

```python
# lambda_handler.py for serverless A2A agent
import json
from mangum import Mangum
from fastapi import FastAPI

app = FastAPI()

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return {...}

@app.post("/a2a/message/send")
async def send_message(request: dict):
    # Process A2A message
    pass

# Lambda handler
handler = Mangum(app)
```

```yaml
# serverless.yml
service: a2a-agent

provider:
  name: aws
  runtime: python3.11

functions:
  agent:
    handler: lambda_handler.handler
    events:
      - httpApi: '*'
```

### Strategy 4: LangGraph Platform (Managed)

```bash
# Deploy to LangGraph Platform (fully managed A2A)
langgraph deploy

# Automatically provides:
# - A2A endpoints
# - Scaling
# - Monitoring
# - Agent Card generation
```

## Migration Checklist

**From Monolithic to Multi-Agent**:

1. **Planning** (1-2 days):
   - [ ] Identify clear specialist to extract
   - [ ] Map dependencies and data flows
   - [ ] Define A2A message contracts

2. **Extract Specialist** (1 week):
   - [ ] Copy relevant code to new service
   - [ ] Add A2A endpoints (agent card, message/send)
   - [ ] Implement authentication
   - [ ] Deploy as separate service

3. **Update Orchestrator** (3-5 days):
   - [ ] Add A2A client for specialist
   - [ ] Update workflow to call specialist
   - [ ] Implement error handling
   - [ ] Add circuit breaker

4. **Testing** (3-5 days):
   - [ ] Unit test specialist agent
   - [ ] Integration test multi-agent workflow
   - [ ] Load test for latency
   - [ ] Test failure scenarios

5. **Production** (2-3 days):
   - [ ] Deploy specialist to production
   - [ ] Monitor latency and errors
   - [ ] Set up alerts
   - [ ] Document A2A contracts

**Total Timeline**: 2-4 weeks for experienced team
