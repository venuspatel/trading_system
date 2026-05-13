#!/bin/bash
# ============================================================
#  TradeAgent V2 — Micro Momentum Mode
#  Alpaca account: PKP3WTGVDUYTDCYW5VDW3Z3CMZ
#  Ports: Backend 8001 · Frontend 3001
# ============================================================

cd "$(dirname "$0")"

echo ""
echo "======================================================"
echo "  TradeAgent V2 — Micro Momentum Mode"
echo "======================================================"

# Kill any existing V2 processes
echo ""
echo "→ Stopping any existing V2 processes..."
lsof -ti:8001,3001 | xargs kill -9 2>/dev/null && echo "  Cleared ports 8001 + 3001" || echo "  Ports already free"
sleep 1

# Start V2 backend on port 8001
echo ""
echo "→ Starting V2 backend on http://localhost:8001 ..."
ALPACA_API_KEY=PKP3WTGVDUYTDCYW5VDW3Z3CMZ \
ALPACA_SECRET_KEY=HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm \
APCA_API_KEY_ID=PKP3WTGVDUYTDCYW5VDW3Z3CMZ \
APCA_API_SECRET_KEY=HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm \
python3 -m uvicorn dashboard.backend.api:app \
  --reload --port 8001 --host 0.0.0.0 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

sleep 3

# Start V2 frontend on port 3001
echo ""
echo "→ Starting V2 frontend on http://localhost:3001 ..."
cd dashboard/frontend

if [ ! -d "node_modules" ]; then
  echo "  Installing Node dependencies (first time only)..."
  npm install
fi

PORT=3001 npm start &
FRONTEND_PID=$!

# Ready
echo ""
echo "======================================================"
echo "  ✅ V2 Agent LIVE — Micro Momentum Mode"
echo ""
echo "  V2 Dashboard → http://localhost:3001"
echo "  V2 API       → http://localhost:8001"
echo ""
echo "  Strategy:    Micro Momentum (scalping)"
echo "  Stop loss:   0.25%"
echo "  Take profit: 0.50%"
echo "  Scan speed:  1 min"
echo "  Conviction:  1.5 minimum"
echo ""
echo "  Press Ctrl+C to stop V2"
echo "======================================================"
echo ""

trap "echo 'Stopping V2...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
