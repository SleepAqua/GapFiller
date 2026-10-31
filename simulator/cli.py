"""Command line front end: run a batch of games and report what happened."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .simulate import _aggregate, load_strategies, run_blocks, summary


def _fmt_table(rows: list[dict]) -> str:
    header = ("strategy", "games", "mean", "se", "upper%", "best", "worst")
    lines = [f"{header[0]:<20}{header[1]:>10}{header[2]:>9}{header[3]:>7}{header[4]:>8}{header[5]:>6}{header[6]:>7}"]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(
            f"{row['strategy']:<20}{row['games']:>10,}{row['mean']:>9.2f}"
            f"{row['se']:>7.2f}{row['upper_bonus_rate'] * 100:>7.1f}%"
            f"{row['best']:>6}{row['worst']:>7}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_simulation.py",
        description="Monte Carlo Yahtzee: play N games per strategy and compare scores.",
    )
    parser.add_argument("--strategies", default="examples/strategies.json")
    parser.add_argument("--rounds", type=int, default=10_000, help="games per strategy")
    parser.add_argument("--chunk", type=int, default=1_000, help="games per reported point")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1, help="processes (0 = all cores)")
    parser.add_argument("--out", default="results.html", help="animated chart output")
    parser.add_argument("--no-viz", action="store_true", help="skip the chart")
    parser.add_argument("--json", dest="json_out", help="write series + summary as JSON")
    parser.add_argument(
        "--optimal",
        action="store_true",
        help="also play the solved optimal policy (solves and caches on first use)",
    )
    args = parser.parse_args(argv)

    if args.rounds <= 0:
        parser.error("--rounds must be positive")
    if args.chunk <= 0:
        parser.error("--chunk must be positive")

    path = Path(args.strategies)
    if not path.exists():
        parser.error(f"strategy file not found: {path}")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if args.optimal:
        spec = dict(spec)
        spec.setdefault("optimal", "optimal")
    try:
        strategies = load_strategies(spec)
    except ValueError as exc:  # a bad rule should read like a config error
        parser.error(f"{path}: {exc}")

    workers = args.workers
    if workers == 0:
        import os

        workers = os.cpu_count() or 1

    started = time.perf_counter()
    blocks = run_blocks(strategies, args.rounds, args.chunk, args.seed, workers)
    elapsed = time.perf_counter() - started
    series = _aggregate(strategies, blocks)
    rows = summary(strategies, blocks)

    print(_fmt_table(rows))
    games = sum(row["games"] for row in rows)
    print(f"\ngames: {games:,}  seed: {args.seed}  workers: {workers}  "
          f"elapsed: {elapsed:.2f}s  ({games / elapsed:,.0f} games/s)")

    if args.json_out:
        out = Path(args.json_out)
        out.write_text(
            json.dumps(
                {
                    "meta": {
                        "seed": args.seed,
                        "rounds": args.rounds,
                        "chunk": args.chunk,
                        "workers": workers,
                        "elapsed_seconds": round(elapsed, 3),
                    },
                    "summary": rows,
                    "series": series,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {out}")

    if not args.no_viz:
        try:
            from viz.animate import build_animation

            target = build_animation(series, out_html=args.out)
            print(f"wrote {target}")
        except Exception as exc:  # charting is a nice-to-have, not the product
            print(f"chart skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
