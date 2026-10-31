#!/usr/bin/env python3
"""Run a batch of games and write the animated comparison.

    ./run.sh --rounds 200000 --workers 8
    ./run.sh --rounds 50000 --chunk 500 --json results.json --no-viz
"""

from simulator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
