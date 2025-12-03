#!/bin/bash
# Start all A2A servers and frontend

set -e

echo "====================================================================="
echo "Starting All Servers with DataPart Implementation"
echo "====================================================================="
echo ""

# Activate virtual environment
source venv/bin/activate

# Kill any existing processes on our ports
echo "Cleaning up existing processes..."
lsof -ti:10001 | xargs kill -9 2>/dev/null || true
lsof -ti:10002 | xargs kill -9 2>/dev/null || true
lsof -ti:10000 | xargs kill -9 2>/dev/null || true
lsof -ti:8080 | xargs kill -9 2>/dev/null || true
sleep 2

echo "Starting Insider Trading Agent (port 10001)..."
python -m alerts.a2a.insider_trading_server --port 10001 > logs/insider_trading.log 2>&1 &
INSIDER_PID=$!
echo "  PID: $INSIDER_PID"
sleep 3

echo "Starting Wash Trade Agent (port 10002)..."
python -m alerts.a2a.wash_trade_server --port 10002 > logs/wash_trade.log 2>&1 &
WASH_PID=$!
echo "  PID: $WASH_PID"
sleep 3

echo "Starting Orchestrator (port 10000)..."
python -m alerts.a2a.orchestrator_server --port 10000 \
  --insider-trading-url http://localhost:10001 \
  --wash-trade-url http://localhost:10002 > logs/orchestrator.log 2>&1 &
ORCH_PID=$!
echo "  PID: $ORCH_PID"
sleep 3

echo "Starting Frontend (port 8080)..."
python -m frontend.app --port 8080 --orchestrator-url http://localhost:10000 > logs/frontend.log 2>&1 &
FRONT_PID=$!
echo "  PID: $FRONT_PID"
sleep 5

echo ""
echo "====================================================================="
echo "All Servers Started!"
echo "====================================================================="
echo "Insider Trading Agent: http://localhost:10001  (PID: $INSIDER_PID)"
echo "Wash Trade Agent:      http://localhost:10002  (PID: $WASH_PID)"
echo "Orchestrator:          http://localhost:10000  (PID: $ORCH_PID)"
echo "Frontend:              http://localhost:8080   (PID: $FRONT_PID)"
echo ""
echo "Logs:"
echo "  - logs/insider_trading.log"
echo "  - logs/wash_trade.log"
echo "  - logs/orchestrator.log"
echo "  - logs/frontend.log"
echo ""
echo "====================================================================="

# Verify servers are running
echo "Verifying servers..."
curl -s http://localhost:10001/.well-known/agent.json | jq -r '.name' || echo "ERROR: Insider Trading Agent not responding"
curl -s http://localhost:10002/.well-known/agent.json | jq -r '.name' || echo "ERROR: Wash Trade Agent not responding"
curl -s http://localhost:10000/.well-known/agent.json | jq -r '.name' || echo "ERROR: Orchestrator not responding"
curl -s http://localhost:8080/ | head -1 || echo "ERROR: Frontend not responding"
echo ""
echo "All servers verified!"
