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

BROWSER=none PORT=3001 npm start &
FRONTEND_PID=$!

echo ""
echo "======================================================"
echo "  V2 Dashboard: http://localhost:3001"
echo "  V2 API:       http://localhost:8001"
echo "  Press Ctrl+C to stop both"
echo "======================================================"
echo ""

# Open dashboard in browser — reuse existing tab if already open
(sleep 6 && osascript -e '
tell application "Google Chrome"
  set found to false
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t contains "localhost:3001" then
        set found to true
        set active tab index of w to index of t
        set index of w to 1
      end if
    end repeat
  end repeat
  if not found then
    open location "http://localhost:3001"
  end if
end tell' 2>/dev/null || open http://localhost:3001) &
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
