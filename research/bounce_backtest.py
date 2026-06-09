#!/usr/bin/env python3
"""
bounce_backtest.py  —  FINAL  (strict filter + regime gate + slippage)

Multi-day, multi-symbol BOUNCE backtest harness.

Reads every *_1min.csv in --data (from fetch_bounce_data.py), splits each into
per-symbol trading days, AUTO-CLASSIFIES each as selloff/recovery/uptrend/chop,
then backtests bounce variants split by regime, with a held-out TEST set and an
optional SLIPPAGE sweep.

FINDINGS (June 2026 study, 25 names x 33d):
  * Premise is real: HL_trail earns on recovery/uptrend days.
  * Thin: gross edge ~+$4/trade, break-even ~2 bps/side slippage.
  * "strict" (good-regime-only entry) cuts cost-bleeding selloff/chop trades,
    pushes break-even past ~3 bps, net-positive on the held-out TEST set, but
    only ~break-even across a full cycle.
  * Verdict: conditionally viable -> tiny PAPER trial, not real capital.

VARIANTS:
  naive_fixedTP : oversold+uptick, fixed 0.25/0.50      (baseline, weak)
  naive_trail   : oversold+uptick, trailing exit        (rides winners)
  HL_trail      : higher-low entry + trailing           (validated core)
  HL_gate       : HL_trail + real-time breadth throttle (cuts selloffs)
  HL_strict     : HL_trail + good-regime-only entry     (best net-of-cost)

HONESTY:
  * stop/target ties -> STOP-FIRST (conservative)
  * trailing fills use bar hi/lo (mildly optimistic)
  * commission $0 (Alpaca); slippage = bps/side, charged entry AND exit
  * regime label is post-hoc (bucketing only); the gate/strict FILTERS use only
    causal info (intraday market breadth so far) -> deployable, not hindsight

USAGE:
  python3 bounce_backtest.py --data ./bounce_data
  python3 bounce_backtest.py --data ./bounce_data --slip 3
  python3 bounce_backtest.py --data ./bounce_data --sweep
  python3 bounce_backtest.py --data ./bounce_data --variants HL_strict,HL_gate
"""
import os, glob, argparse
import numpy as np, pandas as pd
from collections import defaultdict, Counter


def rsi(close, n=14):
    d = close.diff()
    ag = d.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    al = (-d.clip(upper=0)).ewm(com=n-1, min_periods=n).mean()
    return 100 - 100/(1 + ag/al.replace(0, float("inf")))


def load_raw(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, "*_1min.csv")))
    if not files:
        raise SystemExit(f"No *_1min.csv in {data_dir}. Run fetch_bounce_data.py first.")
    raw = {}
    for f in files:
        sym = os.path.basename(f).split("_")[0]
        df = pd.read_csv(f); df["t"] = pd.to_datetime(df["t"])
        df = df.sort_values("t").reset_index(drop=True)
        df["date"] = df["t"].dt.date; df["min"] = df["t"].dt.strftime("%H:%M")
        raw[sym] = df
    return raw


def build_breadth(raw):
    open_by = {}
    for sym, df in raw.items():
        for d, g in df.groupby("date"): open_by[(sym, d)] = g["open"].iloc[0]
    tmp = defaultdict(lambda: defaultdict(list))
    for sym, df in raw.items():
        for d, g in df.groupby("date"):
            o = open_by[(sym, d)]
            for _, r in g.iterrows(): tmp[d][r["min"]].append(1.0 if r["close"] < o else 0.0)
    breadth = defaultdict(dict)
    for d in tmp:
        for m in tmp[d]: breadth[d][m] = float(np.mean(tmp[d][m]))
    return breadth


def classify_regime(day):
    o = day["open"].iloc[0]; c = day["close"].iloc[-1]; move = (c-o)/o
    lo = day["low"].min(); dd = (lo-o)/o; rb = (c-lo)/lo
    if move <= -0.012: return "selloff"
    if dd <= -0.012 and rb >= 0.010 and move > -0.004: return "recovery"
    if move >= 0.012: return "uptrend"
    return "chop"


VARIANTS = {
    "naive_fixedTP": dict(entry="naive", exit="fixed", rsi_max=40, stop=0.0025, tp=0.005, cooldown=15, filter="none"),
    "naive_trail":   dict(entry="naive", exit="trail", rsi_max=45, stop=0.004, trail=0.004, cooldown=15, filter="none"),
    "HL_trail":      dict(entry="hl",    exit="trail", rsi_max=45, stop=0.004, trail=0.004, cooldown=15, filter="none"),
    "HL_gate":       dict(entry="hl",    exit="trail", rsi_max=45, stop=0.004, trail=0.004, cooldown=15, filter="gate"),
    "HL_strict":     dict(entry="hl",    exit="trail", rsi_max=45, stop=0.004, trail=0.004, cooldown=15, filter="strict"),
}


def backtest_day(day, prior, breadth, p, slip_bps, pos_dollars):
    full = pd.concat([prior, day], ignore_index=True) if len(prior) else day.copy()
    f = full.copy(); f["rsi"] = rsi(f["close"])
    offset = len(prior); d = day["date"].iloc[0]; slip = slip_bps/10000.0
    trades = []; in_pos = False; ep = peak = None; last_exit = -10**9
    rsi_max = p["rsi_max"]; stop = p["stop"]; trail = p.get("trail", 0.004)
    tp = p.get("tp", 0.005); cooldown = p["cooldown"]; exit_mode = p["exit"]
    filt = p["filter"]; entry = p["entry"]
    for j in range(len(day)):
        i = offset + j
        if i < 51: continue
        price = f["close"].iloc[i]
        if in_pos:
            hi = f["high"].iloc[i]; lo = f["low"].iloc[i]; peak = max(peak, hi)
            exit_px = None
            if exit_mode == "fixed":
                s = ep*(1-stop); t = ep*(1+tp)
                if lo <= s: exit_px = s
                elif hi >= t: exit_px = t
            else:
                eff = max(ep*(1-stop), peak*(1-trail))
                if lo <= eff: exit_px = eff
            if exit_px is not None:
                trades.append((exit_px-ep)/ep - 2*slip); in_pos = False; last_exit = i; peak = None
                continue
        if not in_pos and (i-last_exit) >= cooldown:
            rv = f["rsi"].iloc[i]
            if not (pd.notna(rv) and rv < rsi_max): continue
            up = f["close"].iloc[i] > f["close"].iloc[i-1]
            if entry == "naive":
                if not (up and f["close"].iloc[i-1] <= f["close"].iloc[i-2]): continue
            else:
                if i < 6: continue
                rl = f["low"].iloc[i-2:i+1].min(); pl = f["low"].iloc[i-5:i-2].min()
                if not (up and rl > pl): continue
            if filt != "none":
                m = day["t"].iloc[j].strftime("%H:%M"); fr = breadth.get(d, {}).get(m, 0.5)
                if filt == "gate":
                    if fr >= 0.70 and rv >= 35: continue
                    if fr >= 0.85: continue
                elif filt == "strict":
                    if fr >= 0.55: continue
                    ups = sum(1 for k in range(3) if f["close"].iloc[i-k] > f["close"].iloc[i-k-1])
                    if ups < 2: continue
            in_pos = True; ep = price; peak = price
    if in_pos:
        trades.append((f["close"].iloc[offset+len(day)-1]-ep)/ep - 2*slip)
    return len(trades), sum(1 for x in trades if x > 0), sum(x*pos_dollars for x in trades)


def build_symbol_days(raw):
    rows = []
    for sym, df in raw.items():
        dates = list(df["date"].unique())
        for k, d in enumerate(dates):
            day = df[df["date"] == d].reset_index(drop=True)
            if len(day) < 60: continue
            prior = df[df["date"] == dates[k-1]].tail(40) if k > 0 else pd.DataFrame()
            rows.append((sym, d, day, prior))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="bounce_data")
    ap.add_argument("--pos", type=float, default=10000.0)
    ap.add_argument("--slip", type=float, default=2.0)
    ap.add_argument("--test_frac", type=float, default=0.3)
    ap.add_argument("--variants", default="")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    raw = load_raw(args.data); breadth = build_breadth(raw); rows = build_symbol_days(raw)
    all_dates = sorted({d for _, d, _, _ in rows})
    n_test = max(1, int(len(all_dates)*args.test_frac)); test_dates = set(all_dates[-n_test:])
    regime_of = {(s, d): classify_regime(day) for s, d, day, _ in rows}

    print(f"Loaded {len(rows)} symbol-days across {len(all_dates)} dates ({len(raw)} symbols).")
    print(f"TRAIN {len(all_dates)-n_test} dates | TEST {n_test} dates (held out).")
    print(f"Regime mix: {dict(Counter(regime_of.values()))}")
    print(f"Position ${args.pos:,.0f}/trade | slippage {args.slip} bps/side\n")

    chosen = [v.strip() for v in args.variants.split(",")] if args.variants else list(VARIANTS)
    regimes = ["selloff", "recovery", "uptrend", "chop"]

    def run(vname, split, slip):
        p = VARIANTS[vname]; agg = defaultdict(lambda: [0, 0, 0.0])
        for sym, d, day, prior in rows:
            it = d in test_dates
            if split == "train" and it: continue
            if split == "test" and not it: continue
            n, w, dol = backtest_day(day, prior, breadth, p, slip, args.pos)
            a = agg[regime_of[(sym, d)]]; a[0]+=n; a[1]+=w; a[2]+=dol
        return agg

    if args.sweep:
        print("SLIPPAGE SWEEP — TEST-set total net P&L by variant\n")
        hdr = f"{'variant':<15}" + "".join(f"{f'{b}bps':>10}" for b in [0,1,2,3,5])
        print(hdr); print("-"*len(hdr))
        for v in chosen:
            line = f"{v:<15}"
            for b in [0,1,2,3,5]:
                agg = run(v, "test", b); tot = sum(agg[r][2] for r in regimes)
                line += f"{f'${tot:+,.0f}':>10}"
            print(line)
        print("\nBreak-even = where it crosses + to -. Liquid large-cap 1-min slip ~1-3 bps/side.")
        return

    for split in ("train", "test"):
        print("="*92); print(f"{split.upper()}  (regime: trades / win% / net$ @ {args.slip}bps)"); print("="*92)
        hdr = f"{'variant':<15}" + "".join(f"{r:>18}" for r in regimes) + f"{'TOTAL':>11}"
        print(hdr); print("-"*len(hdr))
        for v in chosen:
            agg = run(v, split, args.slip); line = f"{v:<15}"; tot = 0.0
            for r in regimes:
                n, w, dol = agg[r]
                cell = f"{n}/{(w/n*100 if n else 0):.0f}%/${dol:+,.0f}" if n else "-"
                line += f"{cell:>18}"; tot += dol
            line += f"{f'${tot:+,.0f}':>11}"; print(line)
        print()
    print("READ: worth a paper trial only if +$ on recovery AND uptrend in BOTH")
    print("train and test at 2-3 bps, and not catastrophic on selloff/chop.")


if __name__ == "__main__":
    main()
