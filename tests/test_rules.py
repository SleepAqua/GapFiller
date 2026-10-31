"""The rule DSL: matching, precedence, and loud failures on typos."""

import unittest

from simulator.rules import Rule, RuleEngine


def state(dice, roll=1, open_categories=None, rolls_left=2):
    return {
        "roll": roll,
        "dice": dice,
        "open_categories": set(open_categories or ("ones", "chance", "yahtzee")),
        "rolls_left": rolls_left,
    }


class RuleValidationTests(unittest.TestCase):
    def test_unknown_condition_key_raises(self):
        with self.assertRaises(ValueError):
            Rule({"rolll": 1}, {"keep_values": [1]})

    def test_unknown_action_key_raises(self):
        with self.assertRaises(ValueError):
            Rule({"roll": 1}, {"keep_faces": [1]})

    def test_rule_needs_exactly_one_action(self):
        with self.assertRaises(ValueError):
            Rule({"roll": 1}, {})
        with self.assertRaises(ValueError):
            Rule({"roll": 1}, {"keep_values": [1], "score_best": True})

    def test_no_condition_matches_everything(self):
        self.assertTrue(Rule({}, {"keep_values": [6]}).matches(state([1, 2, 3, 4, 5])))


class MatchingTests(unittest.TestCase):
    def test_roll_condition_accepts_int_and_list(self):
        rule = Rule({"roll": [1, 2]}, {"keep_values": [6]})
        self.assertTrue(rule.matches(state([6, 1, 2, 3, 4], roll=2)))
        self.assertFalse(rule.matches(state([6, 1, 2, 3, 4], roll=3)))

    def test_category_open_needs_any_overlap(self):
        rule = Rule({"category_open": ["yahtzee"]}, {"score_category": "yahtzee"})
        self.assertTrue(rule.matches(state([1, 1, 1, 1, 1], open_categories=("yahtzee",))))
        self.assertFalse(rule.matches(state([1, 1, 1, 1, 1], open_categories=("ones",))))

    def test_min_count_of_face_accepts_mapping_and_pairs(self):
        as_map = Rule({"min_count_of_face": {"face": 3, "count": 3}}, {"keep_values": [3]})
        as_pairs = Rule({"min_count_of_face": [[3, 3]]}, {"keep_values": [3]})
        dice = [3, 3, 3, 2, 1]
        self.assertTrue(as_map.matches(state(dice)))
        self.assertTrue(as_pairs.matches(state(dice)))
        self.assertFalse(as_map.matches(state([3, 3, 2, 2, 1])))

    def test_min_most_common(self):
        rule = Rule({"min_most_common": 2}, {"keep_most_common": True})
        self.assertTrue(rule.matches(state([5, 5, 1, 2, 3])))
        self.assertFalse(rule.matches(state([5, 4, 1, 2, 3])))

    def test_upper_conditions_read_scorecard_progress(self):
        rule = Rule({"upper_below": 63}, {"keep_values": [6]})
        self.assertTrue(rule.matches(dict(state([6, 1, 2, 3, 4]), upper=0)))
        self.assertTrue(rule.matches(dict(state([6, 1, 2, 3, 4]), upper=62)))
        self.assertFalse(rule.matches(dict(state([6, 1, 2, 3, 4]), upper=63)))
        reached = Rule({"upper_at_least": 63}, {"score_best": True})
        self.assertTrue(reached.matches(dict(state([6, 1, 2, 3, 4]), upper=63)))

    def test_max_rolls_left(self):
        rule = Rule({"max_rolls_left": 0}, {"score_best": True})
        self.assertTrue(rule.matches(state([1, 2, 3, 4, 5], roll=3, rolls_left=0)))
        self.assertFalse(rule.matches(state([1, 2, 3, 4, 5], roll=1, rolls_left=2)))


class EngineTests(unittest.TestCase):
    def test_first_matching_rule_wins(self):
        engine = RuleEngine([
            {"cond": {"min_most_common": 4}, "action": {"keep_values": [6]}},
            {"cond": {"min_most_common": 2}, "action": {"keep_most_common": True}},
        ])
        self.assertEqual(engine.decide_keep(state([6, 6, 6, 6, 1])), [True, True, True, True, False])
        self.assertEqual(engine.decide_keep(state([2, 2, 3, 4, 5])), [True, True, False, False, False])

    def test_no_match_rerolls_everything(self):
        engine = RuleEngine([{"cond": {"roll": 9}, "action": {"keep_values": [1]}}])
        self.assertEqual(engine.decide_keep(state([1, 2, 3, 4, 5])), [False] * 5)

    def test_keep_top_keeps_n_dice(self):
        engine = RuleEngine([{"action": {"keep_top": 2}}])
        mask = engine.decide_keep(state([4, 4, 4, 2, 6]))
        self.assertEqual(sum(mask), 2)
        self.assertTrue(all(d == 4 for d, keep in zip([4, 4, 4, 2, 6], mask) if keep))

    def test_decide_score_returns_category_and_zero_flag(self):
        engine = RuleEngine([{"cond": {"roll": 3}, "action": {"score_category": "Chance"}}])
        self.assertEqual(engine.decide_score(state([1, 2, 3, 4, 5], roll=3)), ("chance", False))
        engine_zero = RuleEngine([{"cond": {"roll": 3}, "action": {"score_zero": "yahtzee"}}])
        self.assertEqual(engine_zero.decide_score(state([1, 2, 3, 4, 5], roll=3)), ("yahtzee", True))

    def test_score_best_means_caller_decides(self):
        engine = RuleEngine([{"cond": {"roll": 3}, "action": {"score_best": True}}])
        self.assertIsNone(engine.decide_score(state([1, 2, 3, 4, 5], roll=3)))


if __name__ == "__main__":
    unittest.main()
