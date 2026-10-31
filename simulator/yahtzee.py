"""Yahtzee scoring rules.

Standard rules as played with five dice and thirteen categories:

* six upper boxes, scored as the sum of matching faces, with a 35-point bonus
  when the upper subtotal reaches 63 (three of each face);
* ``three_kind`` / ``four_kind`` score the sum of all dice when the count is met;
* ``full_house`` 25, ``small_straight`` 30, ``large_straight`` 40, ``yahtzee`` 50;
* ``chance`` scores the dice total;
* each extra Yahtzee after the Yahtzee box is filled with 50 is worth 100.

Not modelled, and documented in the README: the official "Joker" placement rules
for a Yahtzee rolled after the box is used, and scratch/zero placement, which the
policy DSL has no action for.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping, Sequence

FACE_RANGE = range(1, 7)
N_DICE = 5
N_CATEGORIES = 13

UPPER_CATEGORIES = ("ones", "twos", "threes", "fours", "fives", "sixes")
LOWER_CATEGORIES = (
    "three_kind",
    "four_kind",
    "full_house",
    "small_straight",
    "large_straight",
    "yahtzee",
    "chance",
)
ALL_CATEGORIES = UPPER_CATEGORIES + LOWER_CATEGORIES

UPPER_BONUS = 35
UPPER_BONUS_THRESHOLD = 63
YAHTZEE_BONUS = 100

_STRAIGHTS = (
    frozenset({1, 2, 3, 4}),
    frozenset({2, 3, 4, 5}),
    frozenset({3, 4, 5, 6}),
)
_LARGE_STRAIGHTS = (frozenset({1, 2, 3, 4, 5}), frozenset({2, 3, 4, 5, 6}))


def validate_dice(dice: Sequence[int]) -> None:
    if len(dice) != N_DICE:
        raise ValueError(f"expected {N_DICE} dice, got {len(dice)}")
    for die in dice:
        if die not in FACE_RANGE:
            raise ValueError(f"die out of range: {die!r}")


def score_upper(dice: Sequence[int], face: int) -> int:
    return sum(d for d in dice if d == face)


def three_of_a_kind(dice: Sequence[int]) -> int:
    return sum(dice) if max(Counter(dice).values()) >= 3 else 0


def four_of_a_kind(dice: Sequence[int]) -> int:
    return sum(dice) if max(Counter(dice).values()) >= 4 else 0


def full_house(dice: Sequence[int]) -> int:
    counts = sorted(Counter(dice).values())
    return 25 if counts == [2, 3] else 0


def small_straight(dice: Sequence[int]) -> int:
    faces = set(dice)
    return 30 if any(run <= faces for run in _STRAIGHTS) else 0


def large_straight(dice: Sequence[int]) -> int:
    return 40 if frozenset(dice) in _LARGE_STRAIGHTS else 0


def yahtzee(dice: Sequence[int]) -> int:
    return 50 if len(set(dice)) == 1 else 0


def chance(dice: Sequence[int]) -> int:
    return sum(dice)


def is_yahtzee(dice: Sequence[int]) -> bool:
    return len(set(dice)) == 1


def score_category(category: str, dice: Sequence[int]) -> int:
    """Score one category for one roll. Raises on an unknown category."""
    validate_dice(dice)
    cat = category.lower()
    if cat in UPPER_CATEGORIES:
        return score_upper(dice, UPPER_CATEGORIES.index(cat) + 1)
    if cat == "three_kind":
        return three_of_a_kind(dice)
    if cat == "four_kind":
        return four_of_a_kind(dice)
    if cat == "full_house":
        return full_house(dice)
    if cat == "small_straight":
        return small_straight(dice)
    if cat == "large_straight":
        return large_straight(dice)
    if cat == "yahtzee":
        return yahtzee(dice)
    if cat == "chance":
        return chance(dice)
    raise ValueError(f"unknown category: {category!r}")


_UPPER_SCORERS = {
    cat: (lambda dice, face=face: sum(d for d in dice if d == face))
    for face, cat in enumerate(UPPER_CATEGORIES, start=1)
}

_CAT_SCORERS = {
    "three_kind": three_of_a_kind,
    "four_kind": four_of_a_kind,
    "full_house": full_house,
    "small_straight": small_straight,
    "large_straight": large_straight,
    "yahtzee": yahtzee,
    "chance": chance,
}


_SCORERS = {**_UPPER_SCORERS, **_CAT_SCORERS}

_SMALL_MASKS = tuple(sum(1 << (f - 1) for f in run) for run in _STRAIGHTS)
_LARGE_MASKS = tuple(sum(1 << (f - 1) for f in run) for run in _LARGE_STRAIGHTS)


def score_with(category: str, dice: Sequence[int]) -> int:
    """Score one category from the caller's already-counted dice."""
    return _SCORERS[category](dice)


def score_all(dice: Sequence[int], counts: Sequence[int] | None = None) -> dict[str, int]:
    """All thirteen category values for one roll, from a single pass.

    The generic scorers each re-scan the dice; scoring every category this way
    costs about 1 us instead of ~15 us and keeps the Monte Carlo loop honest
    about where its time goes.
    """
    total = dice[0] + dice[1] + dice[2] + dice[3] + dice[4]
    if counts is None:
        counts = [0] * 7
        for die in dice:
            counts[die] += 1
    best_count = max(counts)
    mask = 0
    for face in range(1, 7):
        if counts[face]:
            mask |= 1 << (face - 1)

    scores = {cat: face * counts[face] for face, cat in enumerate(UPPER_CATEGORIES, start=1)}
    scores["three_kind"] = total if best_count >= 3 else 0
    scores["four_kind"] = total if best_count >= 4 else 0
    scores["full_house"] = 25 if best_count == 3 and counts.count(2) == 1 else 0
    scores["small_straight"] = 30 if any(m & ~mask == 0 for m in _SMALL_MASKS) else 0
    scores["large_straight"] = 40 if mask in _LARGE_MASKS else 0
    scores["yahtzee"] = 50 if best_count == 5 else 0
    scores["chance"] = total
    return scores


def best_category_score(dice: Sequence[int], open_categories: Iterable[str]) -> tuple[str, int]:
    """Highest immediate score among the open categories.

    Ties are broken in the canonical ``ALL_CATEGORIES`` order, never by set
    iteration order -- string hashing is randomised per process, so iterating a
    set here would make runs non-reproducible between workers.
    """
    scores = score_all(dice)
    open_set = set(open_categories)
    best_cat: str | None = None
    best_score = -1
    for cat in ALL_CATEGORIES:
        if cat not in open_set:
            continue
        sc = scores[cat]
        if sc > best_score:
            best_score, best_cat = sc, cat
    if best_cat is None:
        raise ValueError("no open categories")
    return best_cat, best_score


def upper_subtotal(scores: Mapping[str, int]) -> int:
    return sum(scores.get(cat, 0) for cat in UPPER_CATEGORIES)


def upper_bonus(scores: Mapping[str, int]) -> int:
    return UPPER_BONUS if upper_subtotal(scores) >= UPPER_BONUS_THRESHOLD else 0


def category_total(scores: Mapping[str, int]) -> int:
    return sum(scores.values())


def game_total(scores: Mapping[str, int], extra_yahtzees: int = 0) -> int:
    """Full scorecard total: categories + upper bonus + Yahtzee bonuses."""
    return category_total(scores) + upper_bonus(scores) + YAHTZEE_BONUS * extra_yahtzees
