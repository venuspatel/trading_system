# -*- coding: utf-8 -*-
"""
DecisionLogger
--------------
Records every decision the agent makes with full reasoning.
Output feeds the live dashboard and daily report.
Each entry is a JSON line — easy to query, stream, and display.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DecisionRecord:
    """One complete decision event — stored in the decision log."""
    timestamp:        str
    symbol:           str
    action:           str           # BUY / SELL / HOLD / BLOCKED
    approach:         str
    conviction_score: float
    buy_signals:      int
    sell_signals:     int
    avg_confidence:   float
    strategies_fired: List[str]
    top_reasons:      List[str]
    risk_approved:    bool
    risk_blocks:      List[str]
    position_shares:  int
    position_dollars: float
    stop_loss:        float
    take_profit:      float
    risk_reward:      float
    portfolio_value:  float
    paper_trade:      bool
    strategy_signals: List[Dict[str, Any]] = field(default_factory=list)
    ai_approved:      Optional[bool]  = None
    ai_confidence:    float           = 0.0
    ai_reasoning:     str             = ""
    ai_concerns:      List[str]       = field(default_factory=list)
    ai_used:          bool            = False
    extra:            Dict[str, Any]  = field(default_factory=dict)


class DecisionLogger:
    """
    Appends every agent decision to a JSONL file.
    The dashboard reads this file to show the decision log in real time.
    """

    def __init__(self, log_path: str = "logs/decisions.jsonl",
                 max_bytes: int = 15_000_000, keep_backups: int = 1):
        self.log_path     = log_path
        self.max_bytes    = max_bytes      # rotate when file exceeds this (~15 MB)
        self.keep_backups = keep_backups   # how many .N rolled files to keep
        self._records   : List[DecisionRecord] = []
        self._load_from_file()

    def _rotate_if_needed(self):
        """Size-based rotation: if the log exceeds max_bytes, roll it to .1
        (shifting older backups) and start a fresh file. Keeps disk bounded
        without losing recent history. Non-fatal on any error."""
        try:
            if not os.path.exists(self.log_path):
                return
            if os.path.getsize(self.log_path) < self.max_bytes:
                return
            # shift existing backups: .1 -> .2, etc., dropping the oldest
            for i in range(self.keep_backups, 0, -1):
                older = f"{self.log_path}.{i}"
                newer = f"{self.log_path}.{i-1}" if i > 1 else self.log_path
                if os.path.exists(newer):
                    if i == self.keep_backups and os.path.exists(older):
                        os.remove(older)          # drop oldest beyond retention
                    os.replace(newer, older)
            # in-memory list also trimmed so dashboard memory stays bounded
            self._records = self._records[-5000:]
        except Exception as exc:
            logger.warning(f"[DecisionLogger] rotation skipped: {exc}")

    def _load_from_file(self):
        """Load existing decisions from disk on startup so memory stays in sync."""
        import json as _json
        try:
            log_dir = os.path.dirname(self.log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            if not os.path.exists(self.log_path):
                return
            with open(self.log_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = _json.loads(line)
                        rec = DecisionRecord(
                            symbol          = d.get("symbol",""),
                            action          = d.get("action","HOLD"),
                            timestamp       = d.get("timestamp",""),
                            conviction_score= d.get("conviction_score",0),
                            shares          = d.get("shares",0),
                            approved        = d.get("approved",False),
                            top_reasons     = d.get("top_reasons",[]),
                            risk_blocks     = d.get("risk_blocks",[]),
                        )
                        self._records.append(rec)
                    except Exception:
                        continue
        except Exception:
            pass  # Non-fatal — start with empty records

    def log(self, record: DecisionRecord):
        """Append a decision record to the log."""
        self._rotate_if_needed()
        self._records.append(record)
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(vars(record)) + "\n")
        except Exception as exc:
            logger.error(f"[DecisionLogger] Failed to write log: {exc}")

        action_icon = {"BUY": "^", "SELL": "v", "HOLD": "-", "BLOCKED": "X"}.get(record.action, "?")
        logger.info(
            f"[Decision] {action_icon} {record.symbol} {record.action} | "
            f"conviction={record.conviction_score:+.2f} | "
            f"buys={record.buy_signals} sells={record.sell_signals} | "
            f"{'PAPER' if record.paper_trade else 'LIVE'}"
        )

    def recent(self, n: int = 50) -> List[DecisionRecord]:
        """Return the N most recent decisions (from memory)."""
        return self._records[-n:]

    def load_from_file(self) -> List[DecisionRecord]:
        """Load all historical decisions from the log file."""
        records = []
        if not os.path.exists(self.log_path):
            return records
        try:
            with open(self.log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        records.append(DecisionRecord(**d))
        except Exception as exc:
            logger.error(f"[DecisionLogger] Failed to read log: {exc}")
        return records

    def today_summary(self) -> Dict:
        """Stats for the current trading day — fed to the dashboard."""
        try:
            from zoneinfo import ZoneInfo as _ZI
            today = datetime.now(_ZI("America/New_York")).date().isoformat()
        except Exception:
            from datetime import timezone as _tz, timedelta as _td
            today = datetime.now(_tz(_td(hours=-4))).date().isoformat()
        today_records = [r for r in self._records if r.timestamp.startswith(today)]
        buys    = [r for r in today_records if r.action == "BUY"]
        sells   = [r for r in today_records if r.action == "SELL"]
        blocked = [r for r in today_records if r.action == "BLOCKED"]
        holds   = [r for r in today_records if r.action == "HOLD"]
        return {
            "date":         today,
            "total_scans":  len(set(r.timestamp[:16] for r in today_records)),  # unique scan cycles
            "buys":         len(buys),
            "sells":        len(sells),
            "blocked":      len(blocked),
            "holds":        len(holds),
            "symbols_traded": list({r.symbol for r in buys + sells}),
            "avg_confidence": round(
                sum(r.avg_confidence for r in buys + sells) / len(buys + sells), 3
            ) if (buys + sells) else 0,
        }
