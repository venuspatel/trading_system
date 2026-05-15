#!/usr/bin/env python3
"""
Feature Flag System — apply_feature_flags.py
=============================================
Applies 3 changes to V1 trading agent:

  1. saved_config.json       — adds feature_flags block (all OFF)
  2. agent_config.py         — reads + stores feature_flags
  3. trailing_stop.py        — Flag 5: trail activation threshold (0.5%)

Run:
    python3 apply_feature_flags.py

Then restart V1:
    lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
    cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh
"""

import json, ast, sys

BASE   = '/Users/venuspatel/Desktop/trading_system/trading_agent'
ERRORS = []

def ok(msg):  print(f"  ✓  {msg}")
def err(msg): print(f"  ✗  {msg}"); ERRORS.append(msg)
def hdr(msg): print(f"\n{'='*60}\n  {msg}\n{'='*60}")

# ─────────────────────────────────────────────────────────────
# PATCH 1 — saved_config.json: add feature_flags block
# ─────────────────────────────────────────────────────────────
hdr("PATCH 1 — saved_config.json")

CONFIG_PATH = f'{BASE}/saved_config.json'
try:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    if 'feature_flags' in cfg:
        ok("feature_flags block already exists — skipping")
    else:
        cfg['feature_flags'] = {
            "trail_activation":         False,   # Flag 5 — 0.5% before trail starts
            "atr_trailing_stops":       False,   # Flag 2 — ATR-based stop distance
            "drawdown_circuit_breaker": False,   # Flag 3 — 5-day rolling drawdown halt
            "sector_concentration":     False,   # Flag 4 — max 40% one sector
            "news_sentiment":           False,   # Flag 1 — news → conviction boost
        }
        with open(CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=2)
        ok("feature_flags block added to saved_config.json")
        print("""
    Current flags (all OFF by default):
      trail_activation         = false   ← Flag 5: enable first
      atr_trailing_stops       = false   ← Flag 2
      drawdown_circuit_breaker = false   ← Flag 3
      sector_concentration     = false   ← Flag 4
      news_sentiment           = false   ← Flag 1: enable last
""")
except Exception as e:
    err(f"saved_config.json patch failed: {e}")

# ─────────────────────────────────────────────────────────────
# PATCH 2 — agent_config.py: read feature_flags from dict
# ─────────────────────────────────────────────────────────────
hdr("PATCH 2 — agent_config.py")

AGENT_CONFIG_PATH = f'{BASE}/decision_engine/agent_config.py'
try:
    with open(AGENT_CONFIG_PATH) as f:
        content = f.read()

    if 'feature_flags' in content:
        ok("feature_flags already in agent_config.py — skipping")
    else:
        # Add feature_flags dataclass field after max_hold_days
        OLD_FIELD = '    max_hold_days:               int   = 2'
        NEW_FIELD = '''    max_hold_days:               int   = 2

    # ── Feature flags ─────────────────────────────────────────
    # All OFF by default. Enable one at a time via dashboard or
    # saved_config.json to test each enhancement independently.
    feature_flags: dict = None   # populated from saved_config.json

    def __post_init__(self):
        if self.feature_flags is None:
            self.feature_flags = {
                "trail_activation":         False,
                "atr_trailing_stops":       False,
                "drawdown_circuit_breaker": False,
                "sector_concentration":     False,
                "news_sentiment":           False,
            }

    def flag(self, name: str) -> bool:
        """Check if a feature flag is enabled. Safe default = False."""
        return bool((self.feature_flags or {}).get(name, False))'''

        if OLD_FIELD in content:
            content = content.replace(OLD_FIELD, NEW_FIELD, 1)

            # Also handle feature_flags in load() — after the existing setattr loop
            OLD_LOAD = '''            elif hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg'''
            NEW_LOAD = '''            elif k == "feature_flags":
                # Merge loaded flags with defaults (handles new flags added later)
                defaults = {
                    "trail_activation":         False,
                    "atr_trailing_stops":       False,
                    "drawdown_circuit_breaker": False,
                    "sector_concentration":     False,
                    "news_sentiment":           False,
                }
                defaults.update(v or {})
                cfg.feature_flags = defaults
            elif hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg'''

            if OLD_LOAD in content:
                content = content.replace(OLD_LOAD, NEW_LOAD, 1)
                ok("feature_flags load handler added")
            else:
                err("Could not find load() pattern — add feature_flags handling manually")

            # Also add to to_dict()
            OLD_DICT = '            "trailing_stop":           self.trailing_stop,'
            NEW_DICT = '''            "feature_flags":          self.feature_flags,
            "trailing_stop":           self.trailing_stop,'''
            if OLD_DICT in content:
                content = content.replace(OLD_DICT, NEW_DICT, 1)
                ok("feature_flags added to to_dict()")
            else:
                err("Could not find to_dict() pattern — add feature_flags manually")

            with open(AGENT_CONFIG_PATH, 'w') as f:
                f.write(content)
            ok("agent_config.py patched with feature_flags field + flag() helper")

        else:
            err(f"Could not find anchor '{OLD_FIELD}' in agent_config.py")

    # Syntax check
    with open(AGENT_CONFIG_PATH) as f:
        src = f.read()
    ast.parse(src)
    ok("agent_config.py syntax OK")

except Exception as e:
    err(f"agent_config.py patch failed: {e}")

# ─────────────────────────────────────────────────────────────
# PATCH 3 — trailing_stop.py: Flag 5 trail activation threshold
# ─────────────────────────────────────────────────────────────
hdr("PATCH 3 — trailing_stop.py (Flag 5: trail activation)")

TRAILING_PATH = f'{BASE}/decision_engine/trailing_stop.py'
try:
    with open(TRAILING_PATH) as f:
        content = f.read()

    if '[TrailFlag5]' in content:
        ok("Flag 5 trail activation already in trailing_stop.py — skipping")
    else:
        # Replace the peak price update block with flag-aware version
        OLD_PEAK = '''            # Update peak price
            if price > state.peak_price:
                state.peak_price = price
                # Move trailing stop up
                if self.config.trailing_stop:
                    new_stop = price * (1 - self.config.trailing_stop_pct)
                    if new_stop > state.current_stop:
                        old_stop = state.current_stop
                        state.current_stop = new_stop
                        logger.debug(
                            f"[TrailingStop] {symbol} peak=${price:.2f} → "
                            f"stop moved ${old_stop:.2f} → ${new_stop:.2f}"
                        )'''

        NEW_PEAK = '''            # Update peak price
            if price > state.peak_price:
                state.peak_price = price
                # Move trailing stop up
                if self.config.trailing_stop:
                    # ── [TrailFlag5] Activation threshold ─────────────────
                    # Flag: trail_activation (default OFF)
                    # When ON:  trail only starts after price moves +0.5%
                    #           from entry. Fixed stop holds until then.
                    #           Prevents wick-noise from firing the trail
                    #           before the move has developed.
                    # When OFF: trail starts immediately (original behavior)
                    _flag_active = (
                        hasattr(self.config, 'flag') and
                        self.config.flag('trail_activation')
                    )
                    ACTIVATION_PCT = 0.005   # +0.5% from entry before trailing

                    if _flag_active:
                        _gain_from_entry = (
                            (price - state.entry_price) / state.entry_price
                            if state.entry_price > 0 else 0
                        )
                        _trail_armed = _gain_from_entry >= ACTIVATION_PCT
                    else:
                        _trail_armed = True   # original behavior — always trail

                    if _trail_armed:
                        new_stop = price * (1 - self.config.trailing_stop_pct)
                        if new_stop > state.current_stop:
                            old_stop = state.current_stop
                            state.current_stop = new_stop
                            logger.debug(
                                f"[TrailingStop] {symbol} peak=${price:.2f} → "
                                f"stop moved ${old_stop:.2f} → ${new_stop:.2f}"
                                + (" [trail armed]" if _flag_active else "")
                            )
                    else:
                        logger.debug(
                            f"[TrailFlag5] {symbol} trail not yet armed — "
                            f"gain={(_gain_from_entry*100):.2f}% < {ACTIVATION_PCT*100:.1f}% "
                            f"activation. Fixed stop at ${state.current_stop:.2f}"
                        )'''

        if OLD_PEAK in content:
            content = content.replace(OLD_PEAK, NEW_PEAK, 1)
            with open(TRAILING_PATH, 'w') as f:
                f.write(content)
            ok("Flag 5 trail activation patch applied to trailing_stop.py")
        else:
            err("Could not find peak price block — spacing may differ. Check manually.")

    # Syntax check
    with open(TRAILING_PATH) as f:
        src = f.read()
    ast.parse(src)
    ok("trailing_stop.py syntax OK")

except Exception as e:
    err(f"trailing_stop.py patch failed: {e}")

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

  Next steps:
    1. Restart V1:
       lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
       cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh

    2. Verify flags loaded:
       curl -s http://localhost:8000/api/state | python3 -m json.tool | grep -A8 feature_flags

    3. Enable Flag 5 (trail activation):
       curl -s http://localhost:8000/api/state | python3 -c "
       import json,sys,urllib.request
       # Or edit saved_config.json directly:
       # set 'trail_activation': true under feature_flags
       "

    4. To toggle any flag manually right now:
       Edit ~/Desktop/trading_system/trading_agent/saved_config.json
       Set 'trail_activation': true under feature_flags
       Agent picks it up next scan cycle (no restart needed)

  Flag enable order (one per week):
    Week 1: trail_activation         ← you are here
    Week 2: sector_concentration
    Week 3: drawdown_circuit_breaker
    Week 4: atr_trailing_stops
    Week 5: news_sentiment
""")
