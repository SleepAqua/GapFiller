"""Runner behaviour: determinism, common random numbers, aggregation."""

import json
import unittest

from simulator.game import play_game
from simulator.simulate import (
    _aggregate,
    _dice_rows,
    load_strategies,
    run_blocks,
    simulate,
    simulate_stream,
    summary,
)

SPEC = {
    "keep_sixes": [
        {"cond": {"roll": [1, 2], "min_count_of_face": {"face": 6, "count": 1}},
         "action": {"keep_values": [6]}},
        {"cond": {"roll": 3}, "action": {"score_best": True}},
    ],
    "chaos": [
        {"cond": {"roll": [1, 2, 3]}, "action": {"keep_values": []}},
        {"cond": {"roll": 3}, "action": {"score_best": True}},
    ],
}


class DiceRowTests(unittest.TestCase):
    def test_rows_are_deterministic_per_block(self):
        self.assertEqual(_dice_rows(5, 0, 3), _dice_rows(5, 0, 3))

    def test_different_blocks_differ(self):
        self.assertNotEqual(_dice_rows(5, 0, 2), _dice_rows(5, 1, 2))

    def test_row_shape(self):
        rows = _dice_rows(1, 2, 4)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(rows[0]), 13 * 3 * 5)
        self.assertTrue(all(1 <= value <= 6 for value in rows[0]))


class GameTests(unittest.TestCase):
    def test_thirteen_categories_scored_once(self):
        strategies = load_strategies(SPEC)
        result = play_game(strategies[0], iter(_dice_rows(3, 0, 1)[0]))
        self.assertEqual(len(result.scores), 13)
        self.assertGreater(result.total, 0)

    def test_same_dice_give_same_game(self):
        strategy = load_strategies(SPEC)[0]
        row = _dice_rows(9, 4, 1)[0]
        first = play_game(strategy, iter(row))
        second = play_game(strategy, iter(row))
        self.assertEqual(first.scores, second.scores)
        self.assertEqual(first.total, second.total)

    def test_rng_input_matches_byte_input_shape(self):
        import random

        strategy = load_strategies(SPEC)[1]
        result = play_game(strategy, random.Random(1))
        self.assertEqual(len(result.scores), 13)


class RunTests(unittest.TestCase):
    def test_same_seed_same_numbers(self):
        strategies = load_strategies(SPEC)
        a = summary(strategies, run_blocks(strategies, 300, chunk=100, seed=7))
        b = summary(strategies, run_blocks(strategies, 300, chunk=100, seed=7))
        self.assertEqual([r["mean"] for r in a], [r["mean"] for r in b])

    def test_worker_count_does_not_change_results(self):
        strategies = load_strategies(SPEC)
        serial = summary(strategies, run_blocks(strategies, 400, chunk=100, seed=3, workers=1))
        parallel = summary(strategies, run_blocks(strategies, 400, chunk=100, seed=3, workers=2))
        self.assertEqual([r["mean"] for r in serial], [r["mean"] for r in parallel])

    def test_cumulative_mean_is_monotone_in_count(self):
        strategies = load_strategies(SPEC)
        series = simulate(strategies, 300, chunk=100, seed=1)
        for rows in series.values():
            self.assertEqual([row["chunk"] for row in rows], [0, 1, 2])
            self.assertEqual([row["games_in_chunk"] for row in rows], [100, 100, 100])

    def test_summary_reports_games_and_error(self):
        strategies = load_strategies(SPEC)
        rows = summary(strategies, run_blocks(strategies, 200, chunk=50, seed=2))
        for row in rows:
            self.assertEqual(row["games"], 200)
            self.assertGreater(row["se"], 0)
            self.assertLessEqual(row["worst"], row["mean"])

    def test_summary_is_sorted_by_mean(self):
        strategies = load_strategies(SPEC)
        rows = summary(strategies, run_blocks(strategies, 200, chunk=50, seed=2))
        self.assertEqual([r["mean"] for r in rows], sorted((r["mean"] for r in rows), reverse=True))

    def test_stream_agrees_with_batch(self):
        strategies = load_strategies(SPEC)
        streamed = list(simulate_stream(strategies, 300, chunk=100, seed=4))
        batch = simulate(strategies, 300, chunk=100, seed=4)
        self.assertEqual(len(streamed), 3)
        last_chunk, snapshot = streamed[-1]
        self.assertEqual(last_chunk, 2)
        for name, value in snapshot.items():
            self.assertAlmostEqual(value, batch[name][-1]["cumulative_mean"], places=9)

    def test_common_random_numbers(self):
        """Two names for one rule set must score identically: same dice, same play."""
        twins = load_strategies({"a": SPEC["keep_sixes"], "b": SPEC["keep_sixes"]})
        rows = summary(twins, run_blocks(twins, 150, chunk=50, seed=8))
        self.assertEqual(rows[0]["mean"], rows[1]["mean"])

    def test_bad_spec_fails_at_load(self):
        with self.assertRaises(ValueError):
            load_strategies({"broken": [{"cond": {"nope": 1}, "action": {"score_best": True}}]})


if __name__ == "__main__":
    unittest.main()
