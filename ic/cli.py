"""Command-line front door for the iron condor toolkit.

    python -m ic.cli fetch     --ticker SPY
    python -m ic.cli recommend --ticker SPY [--json] [--top N]
    python -m ic.cli add       --ticker SPY --expiration 2026-07-31 --contracts 1 \
                               --put-long 590 --put-short 595 --call-short 640 --call-long 645 \
                               --credit 1.20
    python -m ic.cli list
    python -m ic.cli analyze   [--json] [--no-fetch]
    python -m ic.cli close     --id 1 --debit 0.55

Strategy parameters (delta target, DTE window, wings, triggers) can be overridden on any
command via the shared flags below; defaults live in :mod:`ic.config`.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from .config import Config, DEFAULT


def _build_config(args) -> Config:
    """Clone DEFAULT, applying any per-run overrides present on the parsed args."""
    cfg = Config(**vars(DEFAULT))
    for field in ("target_delta", "dte_min", "dte_max", "wing_width",
                  "defense_delta", "min_dte_hold", "profit_take_pct", "r"):
        val = getattr(args, field, None)
        if val is not None:
            setattr(cfg, field, val)
    return cfg


def _add_config_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--target-delta", dest="target_delta", type=float)
    p.add_argument("--dte-min", dest="dte_min", type=int)
    p.add_argument("--dte-max", dest="dte_max", type=int)
    p.add_argument("--wing-width", dest="wing_width", type=float)
    p.add_argument("--defense-delta", dest="defense_delta", type=float)
    p.add_argument("--min-dte-hold", dest="min_dte_hold", type=int)
    p.add_argument("--profit-take-pct", dest="profit_take_pct", type=float)
    p.add_argument("--r", dest="r", type=float)


# --- Commands -------------------------------------------------------------------------

def cmd_fetch(args):
    from . import chain
    cfg = _build_config(args)
    path = chain.write_chain(args.ticker.upper(), cfg)
    df = chain.load_chain(args.ticker.upper())
    print(f"Wrote {len(df)} rows to {path}")


def cmd_recommend(args):
    from . import chain, candidates
    cfg = _build_config(args)
    ticker = args.ticker.upper()
    chain_df = chain.load_chain(ticker) if args.no_fetch else chain.fetch_chain(ticker, cfg)
    cands = candidates.build_condor_candidates(
        chain_df, cfg, ticker, put_delta=args.put_delta, call_delta=args.call_delta)[: args.top]
    if args.json:
        print(json.dumps(cands, indent=2, default=str))
        return
    if not cands:
        print(f"No eligible condors for {ticker} in {cfg.dte_min}-{cfg.dte_max} DTE window.")
        return
    pd_t = args.put_delta if args.put_delta is not None else cfg.target_delta
    cd_t = args.call_delta if args.call_delta is not None else cfg.target_delta
    delta_desc = (f"~{pd_t:.2f}-delta shorts" if pd_t == cd_t
                  else f"skewed shorts (put ~{pd_t:.2f} / call ~{cd_t:.2f})")
    print(f"Top {len(cands)} iron condor candidates for {ticker} "
          f"({delta_desc}, {cfg.dte_min}-{cfg.dte_max} DTE):\n")
    for i, c in enumerate(cands, 1):
        print(f"[{i}] {c['expiration']} ({c['dte']} DTE)  underlying={c['underlying']}")
        print(f"    legs: -{c['put_long_strike']:.0f}P / +{c['put_short_strike']:.0f}P "
              f"... +{c['call_short_strike']:.0f}C / -{c['call_long_strike']:.0f}C")
        print(f"    credit={c['credit']:.2f}  max_loss={c['max_loss']:.2f}  "
              f"width={c['wing_width']:.0f}  credit/width={c['credit_to_width']:.2f}")
        print(f"    breakevens=[{c['lower_breakeven']:.2f}, {c['upper_breakeven']:.2f}]  "
              f"est_PoP={c['est_pop']:.0%}  short_deltas=({c['short_put_delta']:.2f},{c['short_call_delta']:.2f})")
        print(f"    liquidity: avg_spread={c['avg_spread_pct']}  min_OI={c['min_open_interest']:.0f}  "
              f"vol={c['total_volume']:.0f}  score={c['score']}\n")


def cmd_add(args):
    from . import positions
    exp_date = datetime.strptime(args.expiration, "%Y-%m-%d").date()
    dte = args.dte if args.dte is not None else max((exp_date - datetime.now().date()).days, 0)
    pos = {
        "ticker": args.ticker.upper(),
        "expiration": args.expiration,
        "dte_at_open": dte,
        "contracts": args.contracts,
        "put_long_strike": args.put_long,
        "put_short_strike": args.put_short,
        "call_short_strike": args.call_short,
        "call_long_strike": args.call_long,
        "credit_received": args.credit,
        "underlying_at_open": args.underlying,
        "short_put_delta_at_open": args.spd,
        "short_call_delta_at_open": args.scd,
        "notes": args.notes,
    }
    new_id = positions.add(pos)
    print(f"Added position id={new_id} ({args.ticker.upper()} {args.expiration} "
          f"{args.put_short:.0f}/{args.call_short:.0f} short, credit {args.credit})")


def cmd_list(args):
    from . import positions
    df = positions.load()
    if df.empty:
        print("No positions recorded.")
        return
    cols = ["id", "ticker", "status", "expiration", "contracts",
            "put_short_strike", "call_short_strike", "credit_received", "realized_pnl"]
    print(df[cols].to_string(index=False))


def cmd_analyze(args):
    from . import analyze
    cfg = _build_config(args)
    results = analyze.analyze_open(cfg, fetch=not args.no_fetch)
    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return
    if not results:
        print("No open positions to analyze.")
        return
    for r in results:
        print(f"--- Position {r['id']}: {r['ticker']} {r['expiration']} ---")
        if r.get("error"):
            print(f"    ! {r['error']}")
            continue
        print(f"    underlying={r['underlying']}  DTE={r['dte_remaining']}  "
              f"unrealized_PnL={r['unrealized_pnl']}  cost_to_close={r['cost_to_close']}")
        print(f"    short_put {r['short_put_strike']:.0f} (delta {r['short_put_delta']}, "
              f"{r['dist_to_short_put']:+.2f} away)  |  "
              f"short_call {r['short_call_strike']:.0f} (delta {r['short_call_delta']}, "
              f"{r['dist_to_short_call']:+.2f} away)")
        flags = ", ".join(r["triggers"]) if r["triggers"] else "none"
        print(f"    triggers: {flags}\n")


def cmd_regime(args):
    from . import market
    cfg = _build_config(args)
    r = market.regime(args.ticker.upper(), lookback=args.lookback, cfg=cfg)
    if args.json:
        print(json.dumps(r, indent=2, default=str))
        return
    rv = r["realized_vol"]
    print(f"{r['ticker']} regime as of {r['asof']}  (lookback {r['lookback']})")
    print(f"  spot {r['spot']}   SMA20 {r['sma20']}   SMA50 {r['sma50']}   trend: {r['trend'].upper()}")
    print(f"  realized vol: 21d {rv['d21']}%  63d {rv['d63']}%  126d {rv['d126']}%   regime: {r['vol_regime'].upper()}")
    print(f"  ATM IV {r['atm_iv']}% ({r['atm_iv_dte']}d to {r['atm_iv_expiration']})  "
          f"IV-RV premium {r['iv_rv_premium']:+}pts ({r['premium_label']})")
    print(f"  expected 1SD move to {r['atm_iv_dte']}d: +/- {r['expected_move_1sd']} pts")
    for label, w in r["windows"].items():
        print(f"  {label[1:]+'d':>5}: low {w['low']}  high {w['high']}  range {w['range_pct']}%  change {w['change_pct']:+}%")
    print(f"  max drawdown 63d: {r['max_drawdown_63d_pct']}%")


def cmd_close(args):
    from . import positions
    realized = positions.close(args.id, args.debit, args.date)
    print(f"Closed position id={args.id} at debit {args.debit}. Realized P&L = {realized:+.2f}")


# --- Parser ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ic", description="Iron condor toolkit")
    sub = p.add_subparsers(dest="command", required=True)

    pf = sub.add_parser("fetch", help="Fetch and persist an option chain")
    pf.add_argument("--ticker", default="SPY")
    _add_config_flags(pf)
    pf.set_defaults(func=cmd_fetch)

    pr = sub.add_parser("recommend", help="Recommend iron condor candidates")
    pr.add_argument("--ticker", default="SPY")
    pr.add_argument("--top", type=int, default=5)
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--no-fetch", action="store_true", help="Use cached chain CSV instead of fetching")
    pr.add_argument("--put-delta", dest="put_delta", type=float, default=None,
                    help="Override short-PUT target delta (skewed condor)")
    pr.add_argument("--call-delta", dest="call_delta", type=float, default=None,
                    help="Override short-CALL target delta (skewed condor)")
    _add_config_flags(pr)
    pr.set_defaults(func=cmd_recommend)

    pa = sub.add_parser("add", help="Record a manually-filled iron condor")
    pa.add_argument("--ticker", required=True)
    pa.add_argument("--expiration", required=True, help="YYYY-MM-DD")
    pa.add_argument("--contracts", type=int, default=1)
    pa.add_argument("--put-long", dest="put_long", type=float, required=True)
    pa.add_argument("--put-short", dest="put_short", type=float, required=True)
    pa.add_argument("--call-short", dest="call_short", type=float, required=True)
    pa.add_argument("--call-long", dest="call_long", type=float, required=True)
    pa.add_argument("--credit", type=float, required=True, help="Net credit per share")
    pa.add_argument("--underlying", type=float, default=None)
    pa.add_argument("--dte", type=int, default=None)
    pa.add_argument("--spd", type=float, default=None, help="Short put delta at open")
    pa.add_argument("--scd", type=float, default=None, help="Short call delta at open")
    pa.add_argument("--notes", default=None)
    pa.set_defaults(func=cmd_add)

    pl = sub.add_parser("list", help="List recorded positions")
    pl.set_defaults(func=cmd_list)

    pan = sub.add_parser("analyze", help="Analyze open positions and flag triggers")
    pan.add_argument("--json", action="store_true")
    pan.add_argument("--no-fetch", action="store_true", help="Use cached chain CSV instead of fetching")
    _add_config_flags(pan)
    pan.set_defaults(func=cmd_analyze)

    pg = sub.add_parser("regime", help="Analyze recent price history + implied/realized volatility")
    pg.add_argument("--ticker", default="SPY")
    pg.add_argument("--lookback", default="6mo", help="yfinance history period (e.g. 3mo, 6mo, 1y)")
    pg.add_argument("--json", action="store_true")
    _add_config_flags(pg)
    pg.set_defaults(func=cmd_regime)

    pc = sub.add_parser("close", help="Close a position and record realized P&L")
    pc.add_argument("--id", type=int, required=True)
    pc.add_argument("--debit", type=float, required=True, help="Net debit per share to close")
    pc.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to today)")
    pc.set_defaults(func=cmd_close)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
