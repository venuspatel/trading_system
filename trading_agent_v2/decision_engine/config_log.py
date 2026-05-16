# -*- coding: utf-8 -*-
"""
ConfigLog — Append-only audit trail for all AI configuration decisions.

Every AIConfigurator decision (including holds) is recorded here.
Each entry carries a full config snapshot so any state can be reverted.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigLog:
    """
    Thread-safe append-only log stored as newline-delimited JSON.
    Kept in logs/ai_config_log.jsonl
    """

    def __init__(self, path: str = "logs/ai_config_log.jsonl"):
        self._path  = path
        self._lock  = threading.Lock()
        self._cache: List[Dict] = []
        self._loaded = False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def append(self, snapshot) -> str:
        """Append a ConfigSnapshot (or plain dict). Returns entry_id."""
        entry = self._to_dict(snapshot)
        entry.setdefault("entry_id", datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f"))
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        with self._lock:
            self._cache.append(entry)
            try:
                with open(self._path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as e:
                logger.error(f"[ConfigLog] Write failed: {e}")

        return entry["entry_id"]

    def recent(self, limit: int = 50) -> List[Dict]:
        """Return most recent entries, newest first."""
        with self._lock:
            return list(reversed(self._cache[-limit:]))

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Find a specific entry by ID."""
        with self._lock:
            for entry in reversed(self._cache):
                if entry.get("entry_id") == entry_id:
                    return entry
        return None

    def all(self) -> List[Dict]:
        with self._lock:
            return list(self._cache)

    def summary(self) -> Dict:
        """Quick stats for dashboard display."""
        with self._lock:
            total    = len(self._cache)
            expands  = sum(1 for e in self._cache if e.get("decision") == "expand")
            defends  = sum(1 for e in self._cache if e.get("decision") == "defend")
            holds    = sum(1 for e in self._cache if e.get("decision") == "hold")
            watchlist_changes = sum(1 for e in self._cache if e.get("new_watchlist"))
            last = self._cache[-1] if self._cache else {}
        return {
            "total_decisions":    total,
            "expands":            expands,
            "defends":            defends,
            "holds":              holds,
            "watchlist_changes":  watchlist_changes,
            "last_decision":      last.get("decision", "none"),
            "last_trigger":       last.get("trigger", ""),
            "last_timestamp":     last.get("timestamp", ""),
            "last_reasoning":     last.get("reasoning", ""),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self):
        """Load existing log file into memory cache."""
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._cache.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            self._loaded = True
            logger.info(f"[ConfigLog] Loaded {len(self._cache)} entries from {self._path}")
        except Exception as e:
            logger.warning(f"[ConfigLog] Load failed: {e}")

    @staticmethod
    def _to_dict(snapshot) -> Dict:
        """Convert ConfigSnapshot dataclass or plain dict to serialisable dict."""
        if isinstance(snapshot, dict):
            return dict(snapshot)
        try:
            import dataclasses
            if dataclasses.is_dataclass(snapshot):
                return dataclasses.asdict(snapshot)
        except Exception:
            pass
        return vars(snapshot) if hasattr(snapshot, "__dict__") else {}
