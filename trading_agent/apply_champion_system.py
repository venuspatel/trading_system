#!/usr/bin/env python3
"""
Champion Config System — apply_champion_system.py
==================================================
Builds the full 3-layer config system:

  Layer 1: Factory defaults (apply_profit_maximizer)
  Layer 2: saved_config.json (manual saves)
  Layer 3: pm_champion.json (auto-promoted best performer)

4 patches:
  1. execution/portfolio_tracker.py  — daily_summary() helper
  2. decision_engine/trading_agent.py — EOD evaluator + promote logic
  3. dashboard/backend/api.py         — /api/champion + /api/promote + /api/revert
  4. pm_champion.json                 — created empty on first run

Promotion criteria (2 consecutive days):
  - Win rate >= 75%
  - Day P&L >= $300
  - Max drawdown < 3%
  - Min 3 trades per day

Run:
    python3 apply_champion_system.py

Then restart V1:
    lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
    cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh
"""

import json, ast, os, sys
from datetime import datetime, timezone

BASE   = '/Users/venuspatel/Desktop/trading_system/trading_agent'
ERRORS = []

def ok(msg):   print(f"  ✓  {msg}")
def err(msg):  print(f"  ✗  {msg}"); ERRORS.append(msg)
def hdr(msg):  print(f"\n{'='*60}\n  {msg}\n{'='*60}")
def check(path):
    try:
        ast.parse(open(path).read())
        ok(f"{os.path.basename(path)} syntax OK")
    except SyntaxError as e:
        err(f"{os.path.basename(path)} SYNTAX ERROR: {e}")

# ─────────────────────────────────────────────────────────────
# PATCH 1 — portfolio_tracker.py: daily_summary() helper
# ─────────────────────────────────────────────────────────────
hdr("PATCH 1 — portfolio_tracker.py: daily_summary()")

PT_PATH = f'{BASE}/execution/portfolio_tracker.py'
with open(PT_PATH) as f:
    content = f.read()

if 'daily_summary' in content:
    ok("daily_summary() already exists — skipping")
else:
    # Add after the stats() method closing — find the last method before class end
    OLD = '''            {"t": s.timestamp, "v": s.portfolio_value, "dd": s.drawdown}'''
    NEW = '''            {"t": s.timestamp, "v": s.portfolio_value, "dd": s.drawdown}'''

    # Add daily_summary as a new method after stats()
    TARGET = '    def get_strategy_breakdown'
    NEW_METHOD = '''    def daily_summary(self) -> dict:
        """
        Returns today's performance summary for champion evaluation.
        Used by the EOD evaluator in trading_agent.py.
        """
        from datetime import datetime, timezone, timedelta
        ET = timezone(timedelta(hours=-4))
        today = datetime.now(ET).strftime('%Y-%m-%d')
        trades = [t for t in self._closed_trades
                  if (t.exit_time or '').startswith(today)]
        if not trades:
            return {
                'date':        today,
                'trades':      0,
                'win_rate':    0.0,
                'day_pnl':     0.0,
                'max_drawdown':0.0,
                'qualifies':   False,
                'reason':      'No trades today',
            }
        winners  = [t for t in trades if t.is_winner]
        win_rate = len(winners) / len(trades)
        day_pnl  = sum(t.pnl for t in trades)
        max_dd   = max((s.drawdown for s in self._snapshots
                        if (s.timestamp or '').startswith(today)), default=0.0)

        # Promotion criteria
        CRITERIA = {
            'win_rate_min':  0.75,
            'pnl_min':       300.0,
            'drawdown_max':  0.03,
            'trades_min':    3,
        }
        fails = []
        if win_rate < CRITERIA['win_rate_min']:
            fails.append(f"win_rate {win_rate:.0%} < {CRITERIA['win_rate_min']:.0%}")
        if day_pnl < CRITERIA['pnl_min']:
            fails.append(f"P&L ${day_pnl:.0f} < ${CRITERIA['pnl_min']:.0f}")
        if max_dd > CRITERIA['drawdown_max']:
            fails.append(f"drawdown {max_dd:.1%} > {CRITERIA['drawdown_max']:.0%}")
        if len(trades) < CRITERIA['trades_min']:
            fails.append(f"only {len(trades)} trades < {CRITERIA['trades_min']} min")

        return {
            'date':        today,
            'trades':      len(trades),
            'win_rate':    round(win_rate, 4),
            'day_pnl':     round(day_pnl, 2),
            'max_drawdown':round(max_dd, 4),
            'qualifies':   len(fails) == 0,
            'reason':      'All criteria met' if not fails else ' | '.join(fails),
        }

    def get_strategy_breakdown'''

    if TARGET in content:
        content = content.replace(TARGET, NEW_METHOD, 1)
        with open(PT_PATH, 'w') as f:
            f.write(content)
        ok("daily_summary() added to portfolio_tracker.py")
    else:
        err("Could not find insertion point — add daily_summary() manually")

check(PT_PATH)

# ─────────────────────────────────────────────────────────────
# PATCH 2 — trading_agent.py: EOD champion evaluator
# ─────────────────────────────────────────────────────────────
hdr("PATCH 2 — trading_agent.py: EOD champion evaluator")

TA_PATH = f'{BASE}/decision_engine/trading_agent.py'
with open(TA_PATH) as f:
    content = f.read()

if 'champion_evaluator' in content:
    ok("Champion evaluator already in trading_agent.py — skipping")
else:
    # Add after the _scan_cycle method's scan_type == EOD handling
    # Find the _scheduled_scan method and add champion check at EOD
    OLD_SCHED = '''    def _scheduled_scan(self, scan_type: str = "EOD"):'''
    NEW_SCHED = '''    def _evaluate_champion(self):
        """
        EOD champion evaluation — called after every trading day.
        Checks if today's performance qualifies for champion promotion.
        Writes evaluation to logs/champion_eval.json for dashboard to read.
        Two consecutive qualifying days → marks config as 'promote_ready'.
        """
        import json, os
        from datetime import datetime, timezone, timedelta

        try:
            summary = self._portfolio.daily_summary()
            eval_path  = os.path.join(os.path.dirname(__file__),
                                      '..', 'logs', 'champion_eval.json')
            champ_path = os.path.join(os.path.dirname(__file__),
                                      '..', 'logs', 'pm_champion.json')
            eval_path  = os.path.abspath(eval_path)
            champ_path = os.path.abspath(champ_path)

            # Load existing eval history
            history = []
            if os.path.exists(eval_path):
                try:
                    with open(eval_path) as f:
                        data = json.load(f)
                        history = data.get('history', [])
                except Exception:
                    history = []

            # Add today
            history.append(summary)
            history = history[-7:]  # keep last 7 days only

            # Check consecutive qualifying days
            consecutive = 0
            for day in reversed(history):
                if day.get('qualifies'):
                    consecutive += 1
                else:
                    break

            promote_ready = consecutive >= 2
            logger.info(
                f"[Champion] EOD eval: {summary['date']} | "
                f"trades={summary['trades']} win={summary['win_rate']:.0%} "
                f"pnl=${summary['day_pnl']:+.0f} dd={summary['max_drawdown']:.1%} | "
                f"qualifies={summary['qualifies']} | "
                f"consecutive={consecutive} | promote_ready={promote_ready}"
            )

            # Write eval file for dashboard
            eval_data = {
                'updated_at':     datetime.now(timezone.utc).isoformat(),
                'today':          summary,
                'consecutive':    consecutive,
                'promote_ready':  promote_ready,
                'history':        history,
                'criteria': {
                    'win_rate_min':  0.75,
                    'pnl_min':       300.0,
                    'drawdown_max':  0.03,
                    'trades_min':    3,
                    'days_required': 2,
                },
            }
            os.makedirs(os.path.dirname(eval_path), exist_ok=True)
            with open(eval_path, 'w') as f:
                json.dump(eval_data, f, indent=2)

            if promote_ready:
                logger.info(
                    f"[Champion] 🏆 Config qualifies for promotion after "
                    f"{consecutive} consecutive days! "
                    f"Use dashboard to promote → pm_champion.json"
                )

        except Exception as e:
            logger.warning(f"[Champion] EOD eval failed: {e}")

    def _scheduled_scan(self, scan_type: str = "EOD"):'''

    if OLD_SCHED in content:
        content = content.replace(OLD_SCHED, NEW_SCHED, 1)
        ok("_evaluate_champion() method added")
    else:
        err("Could not find _scheduled_scan anchor")

    # Now hook it into the scan cycle at EOD
    OLD_HOOK = '''        if scan_type in ("STARTUP", "INTRADAY") and self._hold_overnight:'''
    NEW_HOOK = '''        # Champion evaluation — runs at EOD only
        if scan_type == "EOD":
            try:
                self._evaluate_champion()
            except Exception as _ce:
                logger.warning(f"[Champion] Eval error: {_ce}")

        if scan_type in ("STARTUP", "INTRADAY") and self._hold_overnight:'''

    if OLD_HOOK in content:
        content = content.replace(OLD_HOOK, NEW_HOOK, 1)
        ok("Champion evaluator hooked into EOD scan cycle")
    else:
        err("Could not find scan_cycle hook anchor")

    with open(TA_PATH, 'w') as f:
        f.write(content)

check(TA_PATH)

# ─────────────────────────────────────────────────────────────
# PATCH 3 — api.py: champion endpoints
# ─────────────────────────────────────────────────────────────
hdr("PATCH 3 — api.py: /api/champion + /api/promote + /api/revert")

API_PATH = f'{BASE}/dashboard/backend/api.py'
with open(API_PATH) as f:
    content = f.read()

if '/api/champion' in content:
    ok("Champion endpoints already in api.py — skipping")
else:
    # Add endpoints before the last app route
    OLD_LAST = '''@app.get("/api/health")'''
    NEW_ENDPOINTS = '''@app.get("/api/champion")
async def get_champion():
    """Return champion eval status + current champion config."""
    import json as _json, os as _os
    BASE_DIR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    eval_path  = _os.path.join(BASE_DIR, "logs", "champion_eval.json")
    champ_path = _os.path.join(BASE_DIR, "logs", "pm_champion.json")
    prev_path  = _os.path.join(BASE_DIR, "logs", "pm_champion_prev.json")

    eval_data  = {}
    champ_data = {}
    prev_data  = {}

    if _os.path.exists(eval_path):
        with open(eval_path) as f:
            eval_data = _json.load(f)
    if _os.path.exists(champ_path):
        with open(champ_path) as f:
            champ_data = _json.load(f)
    if _os.path.exists(prev_path):
        with open(prev_path) as f:
            prev_data = _json.load(f)

    return {
        "eval":     eval_data,
        "champion": champ_data,
        "previous": prev_data,
        "has_champion": bool(champ_data),
        "promote_ready": eval_data.get("promote_ready", False),
    }


@app.post("/api/promote")
async def promote_champion():
    """
    Promote current saved_config.json to pm_champion.json.
    Backs up existing champion to pm_champion_prev.json first.
    Called manually from dashboard when user clicks 'Promote to Default'.
    """
    import json as _json, os as _os, shutil
    BASE_DIR   = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    saved_path = _os.path.join(BASE_DIR, "saved_config.json")
    champ_path = _os.path.join(BASE_DIR, "logs", "pm_champion.json")
    prev_path  = _os.path.join(BASE_DIR, "logs", "pm_champion_prev.json")
    eval_path  = _os.path.join(BASE_DIR, "logs", "champion_eval.json")

    try:
        # Load current saved config
        with open(saved_path) as f:
            saved = _json.load(f)

        # Load eval data for performance stats
        eval_data = {}
        if _os.path.exists(eval_path):
            with open(eval_path) as f:
                eval_data = _json.load(f)

        # Backup existing champion
        if _os.path.exists(champ_path):
            shutil.copy2(champ_path, prev_path)

        # Write new champion
        champion = {
            "promoted_at":   datetime.now(timezone.utc).isoformat(),
            "promoted_from": "saved_config.json",
            "performance":   eval_data.get("today", {}),
            "history":       eval_data.get("history", []),
            "consecutive":   eval_data.get("consecutive", 0),
            "config":        saved,
        }
        _os.makedirs(_os.path.dirname(champ_path), exist_ok=True)
        with open(champ_path, 'w') as f:
            _json.dump(champion, f, indent=2)

        import logging
        logging.getLogger(__name__).info(
            f"[Champion] 🏆 Promoted to champion: "
            f"win={eval_data.get('today',{}).get('win_rate',0):.0%} "
            f"pnl=${eval_data.get('today',{}).get('day_pnl',0):+.0f}"
        )
        return {"status": "promoted", "champion": champion}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/revert")
async def revert_champion():
    """
    Revert to previous champion config.
    Copies pm_champion_prev.json → saved_config.json and reconfigures agent.
    """
    import json as _json, os as _os
    BASE_DIR   = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    saved_path = _os.path.join(BASE_DIR, "saved_config.json")
    prev_path  = _os.path.join(BASE_DIR, "logs", "pm_champion_prev.json")

    if not _os.path.exists(prev_path):
        return {"status": "error", "message": "No previous champion to revert to"}

    try:
        with open(prev_path) as f:
            prev = _json.load(f)

        prev_config = prev.get("config", {})
        if not prev_config:
            return {"status": "error", "message": "Previous champion has no config"}

        # Write back to saved_config.json
        with open(saved_path, 'w') as f:
            _json.dump(prev_config, f, indent=2)

        # Reconfigure live agent
        if _agent:
            cfg = _load_config_from_disk()
            if cfg:
                _agent.reconfigure(cfg)

        import logging
        logging.getLogger(__name__).info("[Champion] Reverted to previous champion config")
        return {"status": "reverted", "config": prev_config}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/health")'''

    if OLD_LAST in content:
        content = content.replace(OLD_LAST, NEW_ENDPOINTS, 1)
        # Need datetime + timezone import at top of the endpoint section
        # Check if already imported
        if 'from datetime import datetime, timezone' not in content:
            content = content.replace(
                'from datetime import datetime, timezone',
                'from datetime import datetime, timezone',
                1
            )
        with open(API_PATH, 'w') as f:
            f.write(content)
        ok("Champion endpoints added to api.py")
    else:
        err("Could not find /api/health anchor — add endpoints manually")

check(API_PATH)

# ─────────────────────────────────────────────────────────────
# PATCH 4 — Create empty champion_eval.json
# ─────────────────────────────────────────────────────────────
hdr("PATCH 4 — Create logs/champion_eval.json")

LOGS_DIR  = f'{BASE}/logs'
EVAL_PATH = f'{LOGS_DIR}/champion_eval.json'

os.makedirs(LOGS_DIR, exist_ok=True)
if os.path.exists(EVAL_PATH):
    ok("champion_eval.json already exists — skipping")
else:
    with open(EVAL_PATH, 'w') as f:
        json.dump({
            "updated_at":    datetime.now(timezone.utc).isoformat(),
            "today":         {},
            "consecutive":   0,
            "promote_ready": False,
            "history":       [],
            "criteria": {
                "win_rate_min":  0.75,
                "pnl_min":       300.0,
                "drawdown_max":  0.03,
                "trades_min":    3,
                "days_required": 2,
            },
        }, f, indent=2)
    ok("logs/champion_eval.json created")

# ─────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────
hdr("SUMMARY")

if ERRORS:
    print(f"  {len(ERRORS)} error(s) — fix before restarting:")
    for e in ERRORS:
        print(f"    • {e}")
    sys.exit(1)
else:
    print("""  All patches applied cleanly.

  How it works:
    • Every EOD scan → _evaluate_champion() checks today's performance
    • 2 consecutive qualifying days → promote_ready = True
    • Dashboard shows "Promote to Default" button
    • You click it → saved_config.json promoted to pm_champion.json
    • If new config underperforms → "Revert" button restores previous champion

  New API endpoints:
    GET  /api/champion  — current champion + eval status
    POST /api/promote   — promote saved_config → pm_champion.json
    POST /api/revert    — restore previous champion

  New files:
    logs/champion_eval.json   — daily evaluation history
    logs/pm_champion.json     — current champion config (created on first promote)
    logs/pm_champion_prev.json — previous champion (backup before promote)

  Next steps:
    1. Restart V1
    2. Add Promote/Revert buttons to dashboard (next session)
    3. After 2 qualifying days → click Promote on dashboard

  Promotion criteria (all must pass for 2 consecutive days):
    ✓ Win rate >= 75%
    ✓ Day P&L   >= $300
    ✓ Drawdown  <  3%
    ✓ Trades    >= 3 per day
""")
