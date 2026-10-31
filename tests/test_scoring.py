"""Scoring rules: the part a simulator must get exactly right."""

import random
import unittest

from simulator.yahtzee import (
    ALL_CATEGORIES,
    UPPER_BONUS,
    UPPER_BONUS_THRESHOLD,
    YAHTZEE_BONUS,
    game_total,
    score_all,
    score_category,
    upper_bonus,
    upper_subtotal,
    validate_dice,
)


class CategoryScoringTests(unittest.TestCase):
    def test_upper_box_counts_matching_faces(self):
        self.assertEqual(score_category("threes", [3, 3, 3, 1, 2]), 9)
        self.assertEqual(score_category("sixes", [6, 1, 2, 3, 4]), 6)
        self.assertEqual(score_category("ones", [2, 3, 4, 5, 6]), 0)

    def test_three_and_four_of_a_kind_need_the_count(self):
        self.assertEqual(score_category("three_kind", [4, 4, 4, 2, 1]), 15)
        self.assertEqual(score_category("three_kind", [4, 4, 2, 2, 1]), 0)
        self.assertEqual(score_category("four_kind", [5, 5, 5, 5, 2]), 22)
        self.assertEqual(score_category("four_kind", [5, 5, 5, 2, 2]), 0)

    def test_full_house(self):
        self.assertEqual(score_category("full_house", [2, 2, 3, 3, 3]), 25)
        self.assertEqual(score_category("full_house", [2, 2, 2, 3, 3]), 25)
        self.assertEqual(score_category("full_house", [2, 2, 2, 2, 2]), 0)
        self.assertEqual(score_category("full_house", [1, 2, 3, 4, 5]), 0)

    def test_straights(self):
        for dice in ([1, 2, 3, 4, 6], [2, 3, 4, 5, 5], [3, 4, 5, 6, 6]):
            self.assertEqual(score_category("small_straight", dice), 30, dice)
        self.assertEqual(score_category("small_straight", [1, 2, 3, 5, 6]), 0)
        self.assertEqual(score_category("large_straight", [1, 2, 3, 4, 5]), 40)
        self.assertEqual(score_category("large_straight", [2, 3, 4, 5, 6]), 40)
        self.assertEqual(score_category("large_straight", [2, 3, 4, 5, 5]), 0)

    def test_yahtzee_and_chance(self):
        self.assertEqual(score_category("yahtzee", [4, 4, 4, 4, 4]), 50)
        self.assertEqual(score_category("yahtzee", [4, 4, 4, 4, 3]), 0)
        self.assertEqual(score_category("chance", [1, 1, 1, 1, 1]), 5)

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            score_category("pair", [1, 2, 3, 4, 5])

    def test_dice_validation(self):
        with self.assertRaises(ValueError):
            validate_dice([1, 2, 3, 4])
        with self.assertRaises(ValueError):
            validate_dice([1, 2, 3, 4, 7])
        validate_dice([1, 2, 3, 4, 6])  # no raise


class UpperBonusTests(unittest.TestCase):
    def test_bonus_needs_63(self):
        under = {"ones": 3, "twos": 6, "threes": 9, "fours": 12, "fives": 15, "sixes": 17}
        self.assertEqual(upper_subtotal(under), 62)
        self.assertEqual(upper_bonus(under), 0)
        at = dict(under, sixes=18)
        self.assertEqual(upper_subtotal(at), UPPER_BONUS_THRESHOLD)
        self.assertEqual(upper_bonus(at), UPPER_BONUS)

    def test_game_total_adds_bonus_and_extra_yahtzees(self):
        scores = {"sixes": 30, "chance": 20}
        self.assertEqual(game_total(scores), 50)
        self.assertEqual(game_total(scores, extra_yahtzees=2), 50 + 2 * YAHTZEE_BONUS)
        perfect_upper = {"ones": 3, "twos": 6, "threes": 9, "fours": 12, "fives": 15, "sixes": 18}
        self.assertEqual(game_total(perfect_upper), 63 + UPPER_BONUS)


class FastScorerEquivalenceTests(unittest.TestCase):
    def test_score_all_matches_category_scorers(self):
        rng = random.Random(11)
        for _ in range(3000):
            dice = [rng.randint(1, 6) for _ in range(5)]
            fast = score_all(dice)
            self.assertEqual(set(fast), set(ALL_CATEGORIES))
            for category in ALL_CATEGORIES:
                self.assertEqual(fast[category], score_category(category, dice), (dice, category))


if __name__ == "__main__":
    unittest.main()
