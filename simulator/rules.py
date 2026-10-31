"""A tiny rule DSL for dice-keeping and scoring decisions.

A strategy is a JSON list of rules; the first rule whose condition matches wins.

    {"cond": {"roll": [1, 2], "min_most_common": 3},
     "action": {"keep_most_common": true}}

Conditions (all optional, all must hold):

    roll             int or list of ints -- which roll number this applies to
    category_open    str or list -- at least one of these is still unscored
    min_count_of_face {"face": n, "count": m} or [[face, count], ...]
    min_most_common  int -- the most frequent face appears at least this often
    max_rolls_left   int -- only if at most this many re-rolls remain
    upper_below      int -- upper-section subtotal so far is below this
    upper_at_least   int -- upper-section subtotal so far has reached this

Actions (exactly one per rule):

    keep_values      list of faces -- keep every die showing one of them
    keep_most_common keep every die showing the most frequent face
    keep_top         int -- keep the n most frequent dice
    score_category   category name -- score here if it is still open
    score_best       true -- score the highest immediate value available
    score_zero       category name -- deliberately take a zero there

Unknown condition or action keys raise ``ValueError`` at load time: a typo in a
strategy file should fail loudly instead of silently making the rule dead.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

KNOWN_CONDITIONS = {
    "roll",
    "category_open",
    "min_count_of_face",
    "min_most_common",
    "max_rolls_left",
    "upper_below",
    "upper_at_least",
}
KNOWN_ACTIONS = {
    "keep_values",
    "keep_most_common",
    "keep_top",
    "score_category",
    "score_best",
    "score_zero",
}


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, (list, tuple, set, frozenset)) else [value]


class Rule:
    """One condition/action pair, with its conditions precompiled."""

    __slots__ = ("cond", "action", "_predicates")

    def __init__(self, cond: dict | None, action: dict | None):
        self.cond = dict(cond or {})
        self.action = dict(action or {})
        unknown_cond = set(self.cond) - KNOWN_CONDITIONS
        unknown_action = set(self.action) - KNOWN_ACTIONS
        if unknown_cond:
            raise ValueError(f"unknown condition key(s): {sorted(unknown_cond)}")
        if unknown_action:
            raise ValueError(f"unknown action key(s): {sorted(unknown_action)}")
        if not self.action:
            raise ValueError("rule has no action")
        if len(self.action) > 1:
            raise ValueError(f"rule has more than one action: {sorted(self.action)}")
        self._predicates = [self._compile(key) for key in self.cond]

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        return cls(data.get("cond", {}), data.get("action", {}))

    def _compile(self, key: str):
        value = self.cond[key]
        if key == "roll":
            allowed = frozenset(int(v) for v in _as_list(value))
            return lambda state: state["roll"] in allowed
        if key == "category_open":
            wanted = frozenset(str(v).lower() for v in _as_list(value))
            return lambda state: not wanted.isdisjoint(state["open_categories"])
        if key == "min_count_of_face":
            if isinstance(value, dict):
                if set(value) == {"face", "count"}:  # {"face": 3, "count": 3}
                    wanted_counts = ((int(value["face"]), int(value["count"])),)
                else:  # {"3": 3, "4": 1}
                    wanted_counts = tuple((int(face), int(count)) for face, count in value.items())
            else:  # [[3, 3], [4, 1]]
                wanted_counts = tuple((int(face), int(count)) for face, count in value)

            def count_ok(state):
                dice = state["dice"]
                return all(dice.count(face) >= count for face, count in wanted_counts)

            return count_ok
        if key == "min_most_common":
            threshold = int(value)

            def common_ok(state):
                counts = state.get("counts")
                if counts is None:  # direct API use without precomputed counts
                    counts = Counter(state["dice"]).values()
                return max(counts) >= threshold

            return common_ok
        if key == "max_rolls_left":
            limit = int(value)
            return lambda state: state.get("rolls_left", 0) <= limit
        if key == "upper_below":
            limit = int(value)
            return lambda state: state.get("upper", 0) < limit
        if key == "upper_at_least":
            limit = int(value)
            return lambda state: state.get("upper", 0) >= limit
        raise ValueError(f"unhandled condition: {key}")

    def matches(self, state: dict) -> bool:
        for predicate in self._predicates:
            if not predicate(state):
                return False
        return True

    def apply(self, state: dict) -> dict | None:
        return self.action if self.matches(state) else None


class RuleEngine:
    def __init__(self, rules: Iterable[Rule | dict]):
        self.rules = [r if isinstance(r, Rule) else Rule.from_dict(r) for r in rules]
        # (predicates, action) pairs: skips the per-call method indirection that
        # dominates the hot loop otherwise.
        self._compiled = [(rule._predicates, rule.action) for rule in self.rules]

    def _first_match(self, state: dict) -> dict | None:
        for predicates, action in self._compiled:
            for predicate in predicates:
                if not predicate(state):
                    break
            else:
                return action
        return None

    def decide_keep(self, state: dict, n_dice: int = 5) -> list[bool]:
        """Return a keep mask; if no rule matches, re-roll everything."""
        action = self._first_match(state)
        if action is None:
            return [False] * len(state["dice"])
        dice = state["dice"]
        if "keep_values" in action:
            wanted = set(int(v) for v in _as_list(action["keep_values"]))
            return [die in wanted for die in dice]
        if action.get("keep_most_common"):
            counts = state.get("counts")
            if counts is None:
                face = Counter(dice).most_common(1)[0][0]
            else:
                face = counts.index(max(counts))
            return [die == face for die in dice]
        if "keep_top" in action:
                n = max(0, min(int(action["keep_top"]), n_dice))
                mask = [False] * len(dice)
                kept = 0
                for face, _count in Counter(dice).most_common():
                    for i, die in enumerate(dice):
                        if die == face and not mask[i] and kept < n:
                            mask[i] = True
                            kept += 1
                    if kept >= n:
                        break
                return mask
        return [False] * len(state["dice"])

    def decide_score(self, state: dict) -> tuple[str, bool] | None:
        """Return ``(category, take_zero)`` from a scoring rule, else ``None``."""
        action = self._first_match(state)
        if action is None:
            return None
        if "score_category" in action:
            return str(action["score_category"]).lower(), False
        if "score_zero" in action:
            return str(action["score_zero"]).lower(), True
        return None  # score_best, or a keep-only rule on the final roll
