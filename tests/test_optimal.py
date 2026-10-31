"""The dynamic-programming policy: legal decisions, and a value that survives simulation."""

import unittest
from pathlib import Path

from simulator.game import Strategy, play_game
from simulator.simulate import run_blocks, summary
from simulator.yahtzee import ALL_CATEGORIES

try:
    from simulator import optimal

    HAS_CACHE = optimal.cache_path().exists()
except Exception:  # pragma: no cover - numpy missing or solve never run
    HAS_CACHE = False


@unittest.skipUnless(HAS_CACHE, "optimal policy not solved yet (python -m simulator.optimal)")
class OptimalPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = optimal.OptimalPolicy()

    def test_value_is_in_the_published_neighbourhood(self):
        # Published optimum for Hasbro rules with the forced joker is 254.587729;
        # this engine allows free category choice, so the value sits close by.
        self.assertGreater(self.policy.expected_score, 240.0)
        self.assertLess(self.policy.expected_score, 270.0)

    def test_keep_decisions_are_subsets_of_the_roll(self):
        import random

        rng = random.Random(3)
        for _ in range(200):
            dice = [rng.randint(1, 6) for _ in range(5)]
            state = {
                "roll": 1,
                "dice": dice,
                "open_categories": frozenset(ALL_CATEGORIES),
                "rolls_left": 2,
                "upper": 0,
                "yahtzee_fifty": False,
            }
            keep = self.policy.decide_keep(state)
            self.assertEqual(len(keep), 5)
            # the kept dice must be a sub-multiset of the roll
            for face in range(1, 7):
                kept = sum(1 for d, k in zip(dice, keep) if k and d == face)
                rolled = dice.count(face)
                self.assertLessEqual(kept, rolled, (dice, keep))

    def test_score_choice_is_an_open_category(self):
        import random

        rng = random.Random(5)
        open_cats = ["ones", "twos", "chance"]
        for _ in range(100):
            dice = [rng.randint(1, 6) for _ in range(5)]
            state = {
                "roll": 3,
                "dice": dice,
                "open_categories": frozenset(open_cats),
                "rolls_left": 0,
                "upper": 0,
                "yahtzee_fifty": False,
            }
            category, take_zero = self.policy.decide_score(state)
            self.assertIn(category, open_cats)
            self.assertFalse(take_zero)

    def test_simulated_play_matches_the_solved_value(self):
        strategy = Strategy("optimal", "optimal")
        rows = summary([strategy], run_blocks([strategy], 3000, chunk=1000, seed=11))
        mean = rows[0]["mean"]
        self.assertAlmostEqual(mean, self.policy.expected_score, delta=6.0)

    def test_optimal_beats_every_shipped_rule_strategy(self):
        import json

        spec = json.loads(Path("examples/strategies.json").read_text())
        spec["optimal"] = "optimal"
        from simulator.simulate import load_strategies

        strategies = load_strategies(spec)
        rows = summary(strategies, run_blocks(strategies, 1500, chunk=500, seed=12))
        best_rule = max(r["mean"] for r in rows if r["strategy"] != "optimal")
        optimal_row = next(r for r in rows if r["strategy"] == "optimal")
        self.assertGreater(optimal_row["mean"], best_rule + 20)


if __name__ == "__main__":
    unittest.main()
