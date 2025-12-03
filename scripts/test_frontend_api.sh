#!/bin/bash
# Test frontend API with insider trading alert

echo "====================================================================="
echo "Testing Frontend API with Insider Trading Alert"
echo "====================================================================="
echo ""

# Upload the alert
echo "1. Uploading alert..."
RESPONSE=$(curl -s -X POST http://localhost:8080/api/analyze \
  -F "file=@test_data/alerts/alert_genuine.xml")

echo "Upload response:"
echo "$RESPONSE" | jq .
echo ""

# Extract task_id
TASK_ID=$(echo "$RESPONSE" | jq -r '.task_id')
echo "Task ID: $TASK_ID"
echo ""

# Poll for status
echo "2. Polling for status (max 60 seconds)..."
for i in {1..60}; do
  STATUS_RESPONSE=$(curl -s http://localhost:8080/api/status/$TASK_ID)
  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')

  echo "[$i] Status: $STATUS"

  if [ "$STATUS" == "complete" ]; then
    echo ""
    echo "====================================================================="
    echo "ANALYSIS COMPLETE!"
    echo "====================================================================="
    echo ""
    echo "Full response:"
    echo "$STATUS_RESPONSE" | jq .
    echo ""
    echo "Decision determination:"
    echo "$STATUS_RESPONSE" | jq -r '.decision.determination'
    echo ""
    echo "Confidence scores:"
    echo "$STATUS_RESPONSE" | jq '{genuine: .decision.genuine_alert_confidence, false_positive: .decision.false_positive_confidence}'
    echo ""
    echo "SUCCESS: DataPart extraction worked!"
    exit 0
  elif [ "$STATUS" == "error" ]; then
    echo ""
    echo "====================================================================="
    echo "ERROR OCCURRED"
    echo "====================================================================="
    echo "$STATUS_RESPONSE" | jq .
    exit 1
  fi

  sleep 2
done

echo ""
echo "TIMEOUT: Analysis did not complete within 120 seconds"
exit 1
