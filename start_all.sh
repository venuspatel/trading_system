#!/bin/bash
echo "Starting TradeAgent System..."

# Kill existing
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
pkill -f "ngrok" 2>/dev/null
sleep 2

# Start agent
echo "Starting V1 agent..."
cd ~/Desktop/trading_system/trading_agent
bash run_dashboard.sh &
sleep 4

# Start tunnel
echo "Starting permanent tunnel..."
ngrok http 8000 --domain=crispy-recycled-blemish.ngrok-free.dev --log=stdout > ~/Desktop/trading_system/ngrok.log 2>&1 &
sleep 3

# Status check
echo ""
echo "System Status:"
curl -s http://localhost:8000/api/state | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f'  Agent:  {d[\"agent_status\"]} | Equity: \${round(d[\"account\"][\"equity\"]):,}')
except:
    print('  Agent: starting...')
"
echo "  Tunnel: https://crispy-recycled-blemish.ngrok-free.dev"
echo ""
echo "Open TradeAgent on your iPhone"
echo "Press Ctrl+C to stop"
wait
