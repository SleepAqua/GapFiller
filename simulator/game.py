"""One game of Yahtzee under a strategy.

The hot loop lives here; :mod:`simulator.simulate` only deals with batching and
processes. Dice arrive from an iterator, which lets the runner hand over either a
bare RNG (slow, convenient) or a pre-drawn byte row (fast, and identical for
every strategy -- common random numbers).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Sequence

from .rules import RuleEngine
from .yahtzee import (
    ALL_CATEGORIES,
    N_CATEGORIES,
    UPPER_BONUS,
    UPPER_BONUS_THRESHOLD,
    UPPER_CATEGORIES,
    YAHTZEE_BONUS,
    is_yahtzee,
    joker_value,
    best_category_score,
    is_yahtzee,
    score_with,
)

MAX_ROLLS = 3
UPPER_SECTION = frozenset(UPPER_CATEGORIES)
DICE_PER_GAME = N_CATEGORIES * MAX_ROLLS * 5  # 195 die values per game


@dataclass
class GameResult:
    scores: dict[str, int] = field(default_factory=dict)
    extra_yahtzees: int = 0
    upper_subtotal: int = 0
    upper_bonus: int = 0

    @property
    def category_sum(self) -> int:
        return sum(self.scores.values())

    @property
    def total(self) -> int:
        return self.category_sum + self.upper_bonus + YAHTZEE_BONUS * self.extra_yahtzees


OPTIMAL_MARKER = "optimal"


class Strategy:
    """A named policy.

    ``rules`` is a rule list (picklable, so workers can rebuild the strategy) or
    the marker ``"optimal"``, which selects the solved dynamic-programming policy
    instead of a hand-written rule set.
    """

    __slots__ = ("name", "rules", "engine")

    def __init__(self, name: str, rules: Iterable[dict] | str):
        self.name = name
        if isinstance(rules, str):
            if rules != OPTIMAL_MARKER:
                raise ValueError(f"unknown policy marker: {rules!r}")
            from .optimal import OptimalPolicy

            self.rules = OPTIMAL_MARKER
            self.engine = OptimalPolicy()
        else:
            self.rules = list(rules)
            self.engine = RuleEngine(self.rules)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Strategy({self.name!r}, {len(self.rules)} rules)"


def rng_dice(rng) -> Iterator[int]:
    """Infinite die stream from a ``random.Random`` (reference path)."""
    return (rng.randrange(1, 7) for _ in itertools.count())


def _counts(dice: list[int]) -> list[int]:
    """Face counts indexed 1..6, so rules never build a Counter per roll."""
    counts = [0] * 7
    for die in dice:
        counts[die] += 1
    return counts


def play_game(strategy: Strategy, dice_source: Iterator[int] | object) -> GameResult:
    """Play one 13-turn game using ``dice_source`` for every die roll."""
    nxt = getattr(dice_source, "__next__", None)
    if nxt is None:  # a bare RNG was passed: adapt it
        nxt = rng_dice(dice_source).__next__

    engine = strategy.engine
    open_cats: list[str] = list(ALL_CATEGORIES)
    scores: dict[str, int] = {}
    extra_yahtzees = 0
    yahtzee_scored = False
    upper_so_far = 0
    state = {"roll": 1, "dice": [1, 2, 3, 4, 5], "open_categories": frozenset(), "rolls_left": 2}

    for _turn in range(N_CATEGORIES):
        open_set = frozenset(open_cats)
        dice = [nxt(), nxt(), nxt(), nxt(), nxt()]
        counts = _counts(dice)

        for roll_num in (1, 2):
            state["roll"] = roll_num
            state["dice"] = dice
            state["counts"] = counts
            state["open_categories"] = open_set
            state["rolls_left"] = MAX_ROLLS - roll_num
            state["upper"] = upper_so_far
            state["yahtzee_fifty"] = yahtzee_scored
            keep = engine.decide_keep(state)
            if keep[0] or keep[1] or keep[2] or keep[3] or keep[4]:
                dice = [dice[0] if keep[0] else nxt(),
                        dice[1] if keep[1] else nxt(),
                        dice[2] if keep[2] else nxt(),
                        dice[3] if keep[3] else nxt(),
                        dice[4] if keep[4] else nxt()]
            else:
                dice = [nxt(), nxt(), nxt(), nxt(), nxt()]
            counts = _counts(dice)

        state["roll"] = MAX_ROLLS
        state["dice"] = dice
        state["counts"] = counts
        state["rolls_left"] = 0
        state["upper"] = upper_so_far
        state["yahtzee_fifty"] = yahtzee_scored
        choice = engine.decide_score(state)
        if choice is not None and choice[0] in open_set:
            category, take_zero = choice
            score = 0 if take_zero else score_with(category, dice)
            if yahtzee_scored and is_yahtzee(dice):
                score = max(score, joker_value(category, dice))
        else:
            category, score = best_category_score(dice, open_set)
            if yahtzee_scored and is_yahtzee(dice):
                score = max(score, joker_value(category, dice))

        # A Yahtzee rolled after the Yahtzee box holds 50 earns the 100 bonus,
        # whichever category it is used for.
        if yahtzee_scored and is_yahtzee(dice):
            extra_yahtzees += 1

        scores[category] = score
        if category in UPPER_SECTION:
            upper_so_far += score
        if category == "yahtzee":
            yahtzee_scored = score == 50
        open_cats.remove(category)

    upper = (scores.get("ones", 0) + scores.get("twos", 0) + scores.get("threes", 0)
             + scores.get("fours", 0) + scores.get("fives", 0) + scores.get("sixes", 0))
    return GameResult(
        scores=scores,
        extra_yahtzees=extra_yahtzees,
        upper_subtotal=upper,
        upper_bonus=UPPER_BONUS if upper >= UPPER_BONUS_THRESHOLD else 0,
    )
