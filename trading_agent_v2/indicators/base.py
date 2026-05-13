# -*- coding: utf-8 -*-
"""
Base types for all indicators.
Every indicator returns a Signal that the Strategy Engine in Layer 3 consumes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class SignalDirection(Enum):
    BUY       = "BUY"
    SELL      = "SELL"
    NEUTRAL   = "NEUTRAL"


class SignalStrength(Enum):
    STRONG    = 3
    MODERATE  = 2
    WEAK      = 1
    NONE      = 0


@dataclass
class Signal:
    """
    The output of every indicator.
    Layer 3 (Strategy Engine) reads these to make trading decisions.
    """
    indicator:  str                         # e.g. "RSI", "MACD", "BB"
    symbol:     str
    timestamp:  datetime
    direction:  SignalDirection
    strength:   SignalStrength
    value:      float                       # primary indicator value
    details:    Dict[str, Any] = field(default_factory=dict)  # extra context
    reason:     str = ""                   # human-readable explanation

    @property
    def is_actionable(self) -> bool:
        return self.direction != SignalDirection.NEUTRAL and \
               self.strength  != SignalStrength.NONE

    def __str__(self):
        return (f"[{self.indicator}] {self.symbol} | "
                f"{self.direction.value} ({self.strength.name}) | "
                f"value={self.value:.4f} | {self.reason}")
