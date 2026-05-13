# -*- coding: utf-8 -*-
"""
AIReviewer — Claude-powered trade decision reviewer
-----------------------------------------------------
Sits between the DecisionEngine and Executor.
Before any BUY or SELL is executed, this reviewer:

  1. Builds a structured prompt with all signal data
  2. Sends it to Claude via the Anthropic API
  3. Gets back a structured JSON verdict:
       - approved: bool
       - confidence: float (0-1)
       - reasoning: str (plain English explanation)
       - concerns: List[str]
       - suggestion: str
  4. Attaches the AI verdict to the TradeDecision
  5. Can VETO trades where AI confidence is too low

The AI reviewer only fires on actionable decisions (BUY/SELL).
HOLD and BLOCKED decisions are passed through without API calls
to keep costs low.

Usage:
    reviewer = AIReviewer()
    verdict  = reviewer.review(decision, report, df, portfolio_context)
    if verdict.approved:
        executor.execute(decision)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import urllib.request

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-sonnet-4-20250514"
MAX_TOKENS        = 600


@dataclass
class AIVerdict:
    """Claude's verdict on a proposed trade."""
    approved:     bool
    confidence:   float          # 0.0 - 1.0
    reasoning:    str            # Plain English explanation
    concerns:     List[str]      = field(default_factory=list)
    suggestion:   str            = ""
    raw_response: str            = ""
    used_ai:      bool           = True
    error:        Optional[str]  = None

    def __str__(self):
        icon = "✓" if self.approved else "✗"
        return (
            f"AI {icon} | confidence={self.confidence:.0%} | "
            f"{self.reasoning[:80]}..."
        )


class AIReviewer:
    """
    Uses Claude to review trade decisions before execution.

    Reads ANTHROPIC_API_KEY from environment.
    If key is not set, falls back to pass-through mode
    (all decisions approved, no AI reasoning).
    """

    def __init__(
        self,
        api_key:          Optional[str] = None,
        min_ai_confidence: float        = 0.60,
        veto_enabled:      bool         = True,
    ):
        self.api_key           = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.min_ai_confidence = min_ai_confidence
        self.veto_enabled      = veto_enabled
        self._enabled          = bool(self.api_key)

        if self._enabled:
            logger.info("[AIReviewer] Enabled — Claude will review all BUY/SELL decisions")
        else:
            logger.warning("[AIReviewer] No API key — running in pass-through mode")

    def review(
        self,
        symbol:            str,
        action:            str,
        conviction_score:  float,
        strategies_fired:  List[str],
        top_reasons:       List[str],
        buy_signals:       int,
        sell_signals:      int,
        price:             float,
        stop_loss:         float,
        take_profit:       float,
        shares:            int,
        dollar_amount:     float,
        portfolio_value:   float,
        open_positions:    Dict,
        df:                Optional[pd.DataFrame] = None,
    ) -> AIVerdict:
        """
        Review a proposed trade and return Claude's verdict.
        Only fires for BUY and SELL actions.
        """
        if action not in ("BUY", "SELL"):
            return AIVerdict(
                approved   = True,
                confidence = 1.0,
                reasoning  = "Pass-through — only BUY/SELL decisions are reviewed",
                used_ai    = False,
            )

        if not self._enabled:
            return AIVerdict(
                approved   = True,
                confidence = 0.75,
                reasoning  = "AI reviewer not configured — add ANTHROPIC_API_KEY to .env to enable",
                used_ai    = False,
            )

        prompt = self._build_prompt(
            symbol, action, conviction_score, strategies_fired,
            top_reasons, buy_signals, sell_signals, price,
            stop_loss, take_profit, shares, dollar_amount,
            portfolio_value, open_positions, df,
        )

        try:
            raw = self._call_claude(prompt)
            verdict = self._parse_response(raw, action)
            logger.info(
                f"[AIReviewer] {symbol} {action} — "
                f"AI {'APPROVED' if verdict.approved else 'VETOED'} "
                f"({verdict.confidence:.0%}) — {verdict.reasoning[:60]}"
            )
            return verdict
        except Exception as e:
            logger.warning(f"[AIReviewer] API call failed: {e} — approving by default")
            return AIVerdict(
                approved   = True,
                confidence = 0.70,
                reasoning  = "AI review unavailable — approved by default",
                used_ai    = False,
                error      = str(e),
            )

    def _build_prompt(
        self, symbol, action, conviction, strategies, reasons,
        buys, sells, price, stop, target, shares, amount,
        portfolio_value, open_positions, df,
    ) -> str:
        """Build the structured prompt for Claude."""

        # Recent price action summary
        price_context = ""
        if df is not None and len(df) >= 5:
            recent = df.tail(5)
            changes = []
            for i in range(1, len(recent)):
                chg = (recent["close"].iloc[i] - recent["close"].iloc[i-1]) / recent["close"].iloc[i-1] * 100
                changes.append(f"{chg:+.1f}%")
            price_context = f"Last 5 days: {', '.join(changes)}"
            vol_avg = df["volume"].tail(20).mean()
            vol_cur = df["volume"].iloc[-1]
            vol_ratio = vol_cur / vol_avg if vol_avg > 0 else 1
            price_context += f" | Volume: {vol_ratio:.1f}x average"

        # Risk/reward summary
        rr = ((target - price) / (price - stop)) if action == "BUY" and stop > 0 and price > stop else 0
        position_pct = (amount / portfolio_value * 100) if portfolio_value > 0 else 0

        open_pos_str = ", ".join(open_positions.keys()) if open_positions else "none"

        prompt = f"""You are a senior quantitative trading analyst reviewing an autonomous trading agent's proposed trade. 
Evaluate this decision and respond with a JSON verdict only — no other text.

PROPOSED TRADE:
- Symbol: {symbol}
- Action: {action}
- Price: ${price:.2f}
- Shares: {shares} (${amount:.0f} = {position_pct:.1f}% of portfolio)
- Stop loss: ${stop:.2f} ({abs(price-stop)/price*100:.1f}% risk)
- Take profit: ${target:.2f} ({abs(target-price)/price*100:.1f}% upside)
- Risk/reward ratio: {rr:.1f}:1

SIGNAL ANALYSIS:
- Conviction score: {conviction:+.2f} (scale -10 to +10)
- Strategies agreeing: {buys} BUY, {sells} SELL
- Strategies fired: {', '.join(strategies[:5]) if strategies else 'none'}
- Top reasons: {'; '.join(reasons[:3]) if reasons else 'none'}
{price_context}

PORTFOLIO CONTEXT:
- Portfolio value: ${portfolio_value:,.0f}
- Open positions: {open_pos_str}

Respond ONLY with this JSON — no preamble, no markdown:
{{
  "approved": true or false,
  "confidence": 0.0 to 1.0,
  "reasoning": "one clear sentence explaining your decision",
  "concerns": ["concern1", "concern2"],
  "suggestion": "one actionable suggestion if any"
}}

Approve if: conviction > 1.5, R:R > 1.5:1, strategies agree, no obvious red flags.
Veto if: R:R < 1:1, conviction weak, against strong trend, or high portfolio concentration."""

        return prompt

    def _call_claude(self, prompt: str) -> str:
        """Call the Anthropic API directly via urllib."""
        payload = json.dumps({
            "model":      MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            data    = payload,
            method  = "POST",
            headers = {
                "Content-Type":      "application/json",
                "x-api-key":         self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return data["content"][0]["text"]

    def _parse_response(self, raw: str, action: str) -> AIVerdict:
        """Parse Claude's JSON response into an AIVerdict."""
        # Strip any markdown fences just in case
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = "\n".join(text.split("\n")[:-1])
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the text
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Could not parse JSON from response: {text[:100]}")

        confidence = float(data.get("confidence", 0.7))
        approved   = bool(data.get("approved", True))

        # Apply veto if confidence is below threshold
        if self.veto_enabled and confidence < self.min_ai_confidence:
            approved = False

        return AIVerdict(
            approved     = approved,
            confidence   = confidence,
            reasoning    = str(data.get("reasoning", "")),
            concerns     = list(data.get("concerns", [])),
            suggestion   = str(data.get("suggestion", "")),
            raw_response = raw,
            used_ai      = True,
        )
