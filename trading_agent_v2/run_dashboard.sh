#!/bin/bash
# Run TradeAgent V2 Dashboard — Experiment Agent
# Usage: ./run_dashboard.sh

echo ""
echo "======================================================"
echo "  TradeAgent V2 — Experiment Agent"
echo "======================================================"
echo ""

cd "$(dirname "$0")"

# Check Python deps
python3 -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "Installing Python dependencies..."
  pip3 install fastapi uvicorn python-multipart
}

# Start backend on port 8001
echo "Starting backend on http://localhost:8001"
python3 -m uvicorn dashboard.backend.api:app --reload --port 8001 --host 0.0.0.0 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

sleep 2

# Start frontend on port 3001
echo ""
echo "Starting frontend on http://localhost:3001"
cd dashboard/frontend

if [ ! -d "node_modules" ]; then
  echo "Installing Node dependencies (first time only)..."
  npm install
fi

PORT=3001 npm start &
FRONTEND_PID=$!
sleep 3 && open http://localhost:3001 &

echo ""
echo "======================================================"
echo "  V2 Dashboard: http://localhost:3001"
echo "  V2 API:       http://localhost:8001"
echo "  Press Ctrl+C to stop both"
echo "======================================================"
echo ""

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
