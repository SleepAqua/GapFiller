"""Exact optimal play, solved by dynamic programming.

Why this module exists
----------------------
The optimal policy for this game is known and cannot be expressed in the rule
DSL: the right move depends on the entire scorecard, including how far the
upper section is from its 63-point bonus. Hand-written rules cannot encode that,
so the game is solved instead.

State
-----
``(mask, upper, yahtzee_fifty)`` where

* ``mask`` is the set of categories already scored (13 bits),
* ``upper`` is the upper-section subtotal capped at 63 (the bonus threshold),
* ``yahtzee_fifty`` records whether the Yahtzee box holds 50, which is what
  enables the 100-point bonus.

Value of a turn with the dice in hand:

    E0(d) = max over open c of  score(c, d) + A(next state)
    E1(d) = max over keeps k of  sum over d' P(d' | k) E0(d')
    E2(d) = max over keeps k of  sum over d' P(d' | k) E1(d')
    A(state) = sum over d p(d) E2(d)

``A(empty scorecard)`` is the expected score of perfect play. The upper subtotal
is carried as a vector of 64 values, so one matrix-vector product per level
covers all of them at once.

Published reference point: solitaire Yahtzee under Hasbro rules *with* the
forced-joker rule scores 254.587729 for perfect play (Verhoeff). This engine
allows free category choice after a Yahtzee instead, which is a slightly
different (and slightly better) game -- see the README.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import time
from pathlib import Path
from typing import Iterable

import numpy as np

from .yahtzee import (
    ALL_CATEGORIES,
    JOKER_VALUES,
    UPPER_BONUS,
    UPPER_BONUS_THRESHOLD,
    YAHTZEE_BONUS,
    score_all,
)

N_CATEGORIES = len(ALL_CATEGORIES)
CATEGORY_INDEX = {cat: i for i, cat in enumerate(ALL_CATEGORIES)}
UPPER_CATS = ALL_CATEGORIES[:6]
UPPER_IDX = [CATEGORY_INDEX[c] for c in UPPER_CATS]
LOWER_IDX = [CATEGORY_INDEX[c] for c in ALL_CATEGORIES[6:]]
YAHTZEE_IDX = CATEGORY_INDEX["yahtzee"]
UPPER_ALL_MASK = sum(1 << i for i in UPPER_IDX)
CACHE_VERSION = 7
UPPER_BUCKETS = 64  # capped 0..63


# --------------------------------------------------------------------------
# dice states, keeps, transitions  (all dice outcomes, no sampling)
# --------------------------------------------------------------------------
def _multisets(n_dice: int, n_faces: int = 6) -> list[tuple[int, ...]]:
    out = []
    for combo in itertools.combinations_with_replacement(range(1, n_faces + 1), n_dice):
        counts = [0] * n_faces
        for face in combo:
            counts[face - 1] += 1
        out.append(tuple(counts))
    return out


def _probability(counts: tuple[int, ...], n_dice: int) -> float:
    permutations = math.factorial(n_dice)
    for count in counts:
        permutations //= math.factorial(count)
    return permutations / 6 ** n_dice


DICE_STATES = _multisets(5)
DICE_INDEX = {state: i for i, state in enumerate(DICE_STATES)}
DICE_PROBS = np.array([_probability(s, 5) for s in DICE_STATES], dtype=np.float32)

KEEPS: list[tuple[int, ...]] = []
for size in range(6):
    for combo in itertools.combinations_with_replacement(range(1, 7), size):
        counts = [0] * 6
        for face in combo:
            counts[face - 1] += 1
        KEEPS.append(tuple(counts))
KEEP_INDEX = {keep: i for i, keep in enumerate(KEEPS)}


def _faces(counts: tuple[int, ...]) -> list[int]:
    out: list[int] = []
    for face, count in enumerate(counts, start=1):
        out.extend([face] * count)
    return out


def _build_transition() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    transition = np.zeros((len(KEEPS), len(DICE_STATES)), dtype=np.float32)
    completions = {
        n: [(state, _probability(state, n)) for state in _multisets(n)] if n else [((0,) * 6, 1.0)]
        for n in range(6)
    }
    for k_idx, keep in enumerate(KEEPS):
        free = 5 - sum(keep)
        for comp, prob in completions[free]:
            combined = tuple(a + b for a, b in zip(keep, comp))
            transition[k_idx, DICE_INDEX[combined]] += prob

    lists: list[list[int]] = []
    width = 0
    for dice in DICE_STATES:
        valid = [KEEP_INDEX[k] for k in KEEPS if all(a <= b for a, b in zip(k, dice))]
        lists.append(valid)
        width = max(width, len(valid))
    ids = np.zeros((len(DICE_STATES), width), dtype=np.int32)
    mask = np.zeros((len(DICE_STATES), width), dtype=bool)
    for i, valid in enumerate(lists):
        ids[i, : len(valid)] = valid
        mask[i, : len(valid)] = True
    return transition, ids, mask


TRANSITION, VALID_KEEPS, VALID_MASK = _build_transition()
IS_YAHTZEE = np.array([1.0 if max(s) == 5 else 0.0 for s in DICE_STATES])
SCORES = np.zeros((len(DICE_STATES), N_CATEGORIES), dtype=np.float32)
for _i, _counts in enumerate(DICE_STATES):
    _values = score_all(_faces(_counts), [0, *_counts])
    for _cat, _idx in CATEGORY_INDEX.items():
        SCORES[_i, _idx] = _values[_cat]

NEG = -np.inf
# Once every upper category is scored the subtotal stops mattering, and the value
# is stored at bucket 0 only. Indexing it by a real subtotal reads uninitialised
# memory -- that is what made the first solved values come out ~6 points low.
UPPER_DONE = np.array(
    [bool(mask & UPPER_ALL_MASK == UPPER_ALL_MASK) for mask in range(1 << N_CATEGORIES)]
)


def _max_over_keeps(per_keep: np.ndarray) -> np.ndarray:
    """Best keep per dice state; ``per_keep`` may carry one column per upper bucket."""
    gathered = per_keep[VALID_KEEPS]
    if gathered.ndim == 3:
        mask = VALID_MASK[:, :, None]
    else:
        mask = VALID_MASK
    return np.where(mask, gathered, NEG).max(axis=1)


def _argmax_keep(per_keep: np.ndarray) -> np.ndarray:
    gathered = per_keep[VALID_KEEPS]
    best = np.where(VALID_MASK, gathered, NEG).argmax(axis=1)
    return np.take_along_axis(VALID_KEEPS, best[:, None], axis=1)[:, 0].astype(np.int16)


# --------------------------------------------------------------------------
# dynamic program
# --------------------------------------------------------------------------
def _state_shape() -> tuple[int, int, int]:
    return 1 << N_CATEGORIES, 2, UPPER_BUCKETS


def solve(progress: bool = False) -> dict:
    """Fill A[mask, flag, upper]; return the tables and the empty-scorecard value."""
    started = time.perf_counter()
    values = np.zeros(_state_shape(), dtype=np.float32)
    upper_done = np.array(
        [bool(mask & UPPER_ALL_MASK == UPPER_ALL_MASK) for mask in range(1 << N_CATEGORIES)]
    )
    buckets = np.arange(UPPER_BUCKETS)

    masks_by_popcount: dict[int, list[int]] = {}
    for mask in range(1 << N_CATEGORIES):
        masks_by_popcount.setdefault(bin(mask).count("1"), []).append(mask)

    for count in sorted(masks_by_popcount, reverse=True):
        for mask in masks_by_popcount[count]:
            if count == N_CATEGORIES:
                continue
            flags = (0, 1) if mask >> YAHTZEE_IDX & 1 else (0,)
            open_idx = [i for i in range(N_CATEGORIES) if not mask >> i & 1]
            for flag in flags:
                if UPPER_DONE[mask]:
                    used_buckets = np.array([0])
                else:
                    used_buckets = buckets
                columns = np.full((len(DICE_STATES), len(used_buckets)), NEG)

                for cat_idx in open_idx:
                    if cat_idx in UPPER_IDX:
                        child_mask = mask | 1 << cat_idx
                        child = values[child_mask, flag, :]
                        add = SCORES[:, cat_idx][:, None]
                        # the +35 is paid once, at the moment the subtotal crosses 63
                        crossed = (
                            (used_buckets[None, :] < UPPER_BONUS_THRESHOLD)
                            & (used_buckets[None, :] + add.astype(int) >= UPPER_BONUS_THRESHOLD)
                        )
                        if UPPER_DONE[child_mask]:
                            candidate = add + child[0] + UPPER_BONUS * crossed
                        else:
                            # subtotal after this roll, capped at the bonus threshold
                            idx = np.minimum(
                                UPPER_BONUS_THRESHOLD, used_buckets[None, :] + add.astype(int)
                            )
                            candidate = add + child[idx] + UPPER_BONUS * crossed
                    elif cat_idx == YAHTZEE_IDX:
                        after_50 = values[mask | 1 << cat_idx, 1, :][used_buckets]
                        after_0 = values[mask | 1 << cat_idx, 0, :][used_buckets]
                        is50 = (SCORES[:, cat_idx] == 50).astype(np.float64)[:, None]
                        candidate = SCORES[:, cat_idx][:, None] + (
                            after_50[None, :] * is50 + after_0[None, :] * (1 - is50)
                        )
                    else:
                        child = values[mask | 1 << cat_idx, flag, used_buckets]
                        candidate = SCORES[:, cat_idx][:, None] + child[None, :]

                    if flag:
                        candidate = candidate + YAHTZEE_BONUS * IS_YAHTZEE[:, None]
                        joker = JOKER_VALUES.get(ALL_CATEGORIES[cat_idx])
                        if joker:
                            candidate = np.maximum(candidate, joker * IS_YAHTZEE[:, None])
                    columns = np.maximum(columns, candidate)

                per_keep = TRANSITION @ columns           # (keeps, buckets)
                e1 = _max_over_keeps(per_keep)
                e2 = _max_over_keeps(TRANSITION @ e1)
                expected = DICE_PROBS @ e2
                if upper_done[mask]:
                    values[mask, flag, 0] = expected[0]
                else:
                    values[mask, flag, :] = expected
        if progress:
            print(f"  masks with {count - 1} scored ...", flush=True)

    elapsed = time.perf_counter() - started
    return {"values": values, "expected_score": float(values[0, 0, 0]), "seconds": elapsed}


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------
def cache_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "optimal_values.npz"


def rules_key() -> str:
    return hashlib.sha256(
        json.dumps([UPPER_BONUS, UPPER_BONUS_THRESHOLD, YAHTZEE_BONUS, CACHE_VERSION, "joker-values"]).encode()
    ).hexdigest()[:12]


def build_and_cache(path: Path | None = None, progress: bool = False) -> dict:
    solution = solve(progress=progress)
    target = path or cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        target,
        values=solution["values"].astype(np.float32),
        rules_key=np.array([rules_key()]),
        expected_score=np.array([solution["expected_score"]]),
    )
    return solution


class OptimalPolicy:
    """Rule-engine look-alike backed by the solved value function.

    Decisions are recomputed per (mask, upper, flag) and memoised, rather than
    shipped as a giant table: one mask level costs two small matrix products.
    """

    def __init__(self, path: Path | None = None):
        target = path or cache_path()
        if not target.exists():
            build_and_cache(target)
        blob = np.load(target)
        if str(blob["rules_key"][0]) != rules_key():
            build_and_cache(target)
            blob = np.load(target)
        self.values = blob["values"].astype(np.float64)
        self.expected_score = float(blob["expected_score"][0])
        self._cache: dict[tuple[int, int, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    # -- decisions ------------------------------------------------------
    def _tables(self, mask: int, flag: int, upper: int):
        key = (mask, flag, min(upper, UPPER_BONUS_THRESHOLD))
        if key in self._cache:
            return self._cache[key]

        mask_, flag_, up = key
        open_idx = [i for i in range(N_CATEGORIES) if not mask_ >> i & 1]
        columns = np.full(len(DICE_STATES), NEG)
        best_cat = np.zeros(len(DICE_STATES), dtype=np.int8)

        if mask_ & UPPER_ALL_MASK == UPPER_ALL_MASK:
            buckets = np.array([0])
        else:
            buckets = np.array([up])

        for cat_idx in open_idx:
            if cat_idx in UPPER_IDX:
                child_mask = mask_ | 1 << cat_idx
                child = self.values[child_mask, flag_, :]
                after = up + SCORES[:, cat_idx].astype(int)
                crossed = (up < UPPER_BONUS_THRESHOLD) & (after >= UPPER_BONUS_THRESHOLD)
                if UPPER_DONE[child_mask]:
                    future = child[0]
                else:
                    future = child[np.minimum(UPPER_BONUS_THRESHOLD, after)]
                candidate = SCORES[:, cat_idx] + future + UPPER_BONUS * crossed
            elif cat_idx == YAHTZEE_IDX:
                after_50 = float(self.values[mask_ | 1 << cat_idx, 1, buckets[0]])
                after_0 = float(self.values[mask_ | 1 << cat_idx, 0, buckets[0]])
                is50 = (SCORES[:, cat_idx] == 50)
                candidate = SCORES[:, cat_idx] + (after_50 * is50 + after_0 * (1 - is50))
            else:
                child = float(self.values[mask_ | 1 << cat_idx, flag_, buckets[0]])
                candidate = SCORES[:, cat_idx] + child

            if flag_:
                candidate = candidate + YAHTZEE_BONUS * IS_YAHTZEE
                joker = JOKER_VALUES.get(ALL_CATEGORIES[cat_idx])
                if joker:
                    candidate = np.maximum(candidate, joker * IS_YAHTZEE)

            better = candidate > columns
            best_cat = np.where(better, np.int8(cat_idx), best_cat)
            columns = np.maximum(columns, candidate)

        per_keep_1 = TRANSITION @ columns
        e1 = _max_over_keeps(per_keep_1)
        keep_1 = _argmax_keep(per_keep_1)
        keep_2 = _argmax_keep(TRANSITION @ e1)

        self._cache[key] = (keep_1, keep_2, best_cat)
        return self._cache[key]

    def _context(self, state: dict) -> tuple[int, int, int]:
        mask = (1 << N_CATEGORIES) - 1
        for cat in state["open_categories"]:
            mask &= ~(1 << CATEGORY_INDEX[cat])
        upper = min(state.get("upper", 0), UPPER_BONUS_THRESHOLD)
        flag = 1 if (mask >> YAHTZEE_IDX & 1) and state.get("yahtzee_fifty") else 0
        return mask, flag, upper

    @staticmethod
    def _dice(dice: Iterable[int]) -> int:
        counts = [0] * 6
        for die in dice:
            counts[die - 1] += 1
        return DICE_INDEX[tuple(counts)]

    def decide_keep(self, state: dict) -> list[bool]:
        mask, flag, upper = self._context(state)
        keep_1, keep_2, _ = self._tables(mask, flag, upper)
        table = keep_2 if state.get("rolls_left", 0) >= 2 else keep_1
        keep = KEEPS[int(table[self._dice(state["dice"])])]
        remaining = list(keep)
        out: list[bool] = []
        for die in state["dice"]:
            if remaining[die - 1]:
                remaining[die - 1] -= 1
                out.append(True)
            else:
                out.append(False)
        return out

    def decide_score(self, state: dict) -> tuple[str, bool] | None:
        mask, flag, upper = self._context(state)
        _, _, best_cat = self._tables(mask, flag, upper)
        return ALL_CATEGORIES[int(best_cat[self._dice(state["dice"])])], False


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Solve optimal play and cache the value function.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()

    target = cache_path()
    if target.exists() and not args.force:
        blob = np.load(target)
        print(f"cached: {target}")
        print(f"E[score] for perfect play: {float(blob['expected_score'][0]):.4f}")
        return 0

    solution = build_and_cache(target, progress=args.progress)
    print(f"solved in {solution['seconds']:.1f}s")
    print(f"E[score] for perfect play: {solution['expected_score']:.4f}")
    print(f"cached: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
