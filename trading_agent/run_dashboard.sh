#!/bin/bash
# Run TradeAgent Dashboard
# Usage: ./run_dashboard.sh

echo ""
echo "======================================================"
echo "  TradeAgent Dashboard"
echo "======================================================"
echo ""

cd "$(dirname "$0")"

# Check Python deps
python3 -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "Installing Python dependencies..."
  pip3 install fastapi uvicorn python-multipart
}

# Start backend
echo "Starting backend on http://localhost:8000"
python3 -m uvicorn dashboard.backend.api:app --reload --port 8000 --host 0.0.0.0 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

sleep 2

# Start frontend
echo ""
echo "Starting frontend on http://localhost:3000"
cd dashboard/frontend

if [ ! -d "node_modules" ]; then
  echo "Installing Node dependencies (first time only)..."
  npm install
fi

npm start &
FRONTEND_PID=$!

echo ""
echo "======================================================"
echo "  Dashboard running at: http://localhost:3000"
echo "  API running at:       http://localhost:8000"
echo "  Press Ctrl+C to stop both"
echo "======================================================"
echo ""

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
