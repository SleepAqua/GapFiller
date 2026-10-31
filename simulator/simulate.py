"""Chunked Monte Carlo runner for the Yahtzee strategy simulator.

Design notes
------------
* **Deterministic.** Every block of games is seeded from ``(seed, block index)``
  alone, so a run is reproducible bit-for-bit for a given seed, chunk size and
  game count -- no matter how many worker processes it is spread over.
* **Common random numbers.** Within a block, every strategy starts from an
  identical RNG stream, so differences between strategies are not inflated by
  luck of the dice.
* **Streaming counters.** A worker aggregates sums in O(1) memory and returns
  counters, not games, so a million-game run never materialises a million rows.
"""

from __future__ import annotations

import hashlib
import math
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator

from .game import DICE_PER_GAME, GameResult, Strategy, play_game
from .yahtzee import ALL_CATEGORIES  # noqa: F401  (re-export for callers)

BlockTask = tuple[int, int, int, int, list]  # strategy idx, block, games, seed, rules


def _seed_for(seed: int, block: int) -> int:
    digest = hashlib.sha256(f"{seed}:{block}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass
class BlockStats:
    block: int
    games: int
    total_score: int
    sum_squares: int
    bonus_games: int
    best: int
    worst: int


def _dice_rows(seed: int, block: int, n_games: int) -> list[bytes]:
    """Pre-draw every die for the block.

    A block is ``n_games * 195`` die values: 13 turns x 3 rolls x 5 dice. Drawing
    them up front means every strategy consumes exactly the same dice, so the
    comparison between strategies is not noise from different luck, and the hot
    loop never touches an RNG.
    """
    try:
        import numpy as np
    except ImportError:  # pure-stdlib fallback, slower but identical in meaning
        rng = random.Random(_seed_for(seed, block))
        return [bytes(rng.randrange(1, 7) for _ in range(DICE_PER_GAME))
                for _ in range(n_games)]
    generator = np.random.Generator(np.random.PCG64(_seed_for(seed, block)))
    grid = generator.integers(1, 7, size=(n_games, DICE_PER_GAME), dtype=np.uint8)
    return [grid[i].tobytes() for i in range(n_games)]


def _run_block(task: BlockTask) -> tuple[int, BlockStats]:
    strategy_idx, block, n_games, seed, rules = task
    strategy = Strategy(f"s{strategy_idx}", rules)
    rows = _dice_rows(seed, block, n_games)
    total = 0
    sum_squares = 0
    bonus_games = 0
    best = -1
    worst = 10**9
    for row in rows:
        result: GameResult = play_game(strategy, iter(row))
        score = result.total
        total += score
        sum_squares += score * score
        if result.upper_bonus:
            bonus_games += 1
        if score > best:
            best = score
        if score < worst:
            worst = score
    return strategy_idx, BlockStats(
        block=block,
        games=n_games,
        total_score=total,
        sum_squares=sum_squares,
        bonus_games=bonus_games,
        best=best,
        worst=worst,
    )


def _blocks(n_games: int, chunk: int) -> int:
    if n_games <= 0:
        raise ValueError("n_games must be positive")
    if chunk <= 0:
        raise ValueError("chunk must be positive")
    return math.ceil(n_games / chunk)


def _tasks(strategies: list[Strategy], n_games: int, chunk: int, seed: int) -> list[BlockTask]:
    total_blocks = _blocks(n_games, chunk)
    out: list[BlockTask] = []
    for idx, strategy in enumerate(strategies):
        for block in range(total_blocks):
            games = min(chunk, n_games - block * chunk)
            out.append((idx, block, games, seed, strategy.rules))
    return out


def _aggregate(
    strategies: list[Strategy],
    results: dict[int, list[BlockStats]],
) -> dict[str, list[dict]]:
    series: dict[str, list[dict]] = {s.name: [] for s in strategies}
    for idx, strategy in enumerate(strategies):
        cumulative = 0
        counts = 0
        for stats in sorted(results[idx], key=lambda s: s.block):
            cumulative += stats.total_score
            counts += stats.games
            series[strategy.name].append(
                {
                    "chunk": stats.block,
                    "games_in_chunk": stats.games,
                    "cumulative_mean": cumulative / counts,
                }
            )
    return series


def run_blocks(
    strategies: list[Strategy],
    n_games: int,
    chunk: int = 10_000,
    seed: int = 0,
    workers: int = 1,
    progress: Callable[[int], None] | None = None,
) -> dict[int, list[BlockStats]]:
    """Run every (strategy, block) task, serially or across processes."""
    tasks = _tasks(strategies, n_games, chunk, seed)
    results: dict[int, list[BlockStats]] = {i: [] for i in range(len(strategies))}
    if workers <= 1:
        for task in tasks:
            idx, stats = _run_block(task)
            results[idx].append(stats)
            if progress:
                progress(1)
        return results

    with ProcessPoolExecutor(max_workers=workers) as pool:
        for idx, stats in pool.map(_run_block, tasks, chunksize=1):
            results[idx].append(stats)
            if progress:
                progress(1)
    return results


def simulate(
    strategies: list[Strategy],
    n_games: int,
    chunk: int = 10_000,
    seed: int = 0,
    workers: int = 1,
) -> dict[str, list[dict]]:
    """Cumulative mean score per strategy, one entry per chunk."""
    return _aggregate(strategies, run_blocks(strategies, n_games, chunk, seed, workers))


def summary(
    strategies: list[Strategy],
    results: dict[int, list[BlockStats]],
) -> list[dict]:
    """Per-strategy totals: mean, standard error, upper-bonus rate, best/worst."""
    rows = []
    for idx, strategy in enumerate(strategies):
        blocks = results[idx]
        games = sum(b.games for b in blocks)
        total = sum(b.total_score for b in blocks)
        sumsq = sum(b.sum_squares for b in blocks)
        mean = total / games
        variance = max(sumsq / games - mean * mean, 0.0)
        rows.append(
            {
                "strategy": strategy.name,
                "games": games,
                "mean": mean,
                "se": math.sqrt(variance / games),
                "upper_bonus_rate": sum(b.bonus_games for b in blocks) / games,
                "best": max(b.best for b in blocks),
                "worst": min(b.worst for b in blocks),
            }
        )
    return sorted(rows, key=lambda r: r["mean"], reverse=True)


def simulate_stream(
    strategies: list[Strategy],
    n_games: int,
    chunk: int = 2_000,
    seed: int = 0,
) -> Iterator[tuple[int, dict[str, float]]]:
    """Sequential generator of cumulative means, for the live web view."""
    cumulative = {s.name: 0.0 for s in strategies}
    counts = {s.name: 0 for s in strategies}
    total_blocks = _blocks(n_games, chunk)
    for block in range(total_blocks):
        games = min(chunk, n_games - block * chunk)
        for idx, strategy in enumerate(strategies):
            _, stats = _run_block((idx, block, games, seed, strategy.rules))
            cumulative[strategy.name] += stats.total_score
            counts[strategy.name] += stats.games
        yield block, {name: cumulative[name] / counts[name] for name in cumulative}


def load_strategies(spec: dict[str, list[dict]]) -> list[Strategy]:
    return [Strategy(name, rules) for name, rules in spec.items()]


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    from .cli import main

    raise SystemExit(main(sys.argv[1:]))
