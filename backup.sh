#!/bin/bash
cd ~/Desktop/trading_system
git add -A
git diff --staged --quiet || git commit -m "Auto backup $(date '+%Y-%m-%d %H:%M')"
git push origin master
