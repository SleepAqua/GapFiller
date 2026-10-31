# Strategies, explained

Every strategy here is either a JSON rule list (the DSL) or the solved optimal
policy. This document explains what each one actually does, what it scores, and
why — plus why the optimal policy cannot be written in that JSON.

Numbers below come from one reproducible run:

```bash
./run.sh --rounds 20000 --chunk 2000 --workers 8 --optimal --no-viz
# all strategies share the same dice (common random numbers), seed 0
```

| strategy | mean | se | upper bonus | best | worst |
|---|---|---|---|---|---|
| optimal (solved) | 253.68 | 0.41 | 68.1% | 672 | 90 |
| upper_plan | 156.16 | 0.40 | 5.0% | 657 | 49 |
| high_faces | 138.19 | 0.28 | 0.8% | 498 | 37 |
| heuristic_benchmark | 130.12 | 0.41 | 1.7% | 693 | 39 |
| chase_yahtzee | 118.53 | 0.27 | 3.8% | 828 | 40 |
| random | 111.60 | 0.20 | 0.0% | 343 | 31 |

---

## How the DSL works

A strategy is a list of rules; the **first** rule whose conditions all hold is
applied, and rules are checked again on every roll.

Conditions: `roll`, `category_open`, `min_count_of_face`, `min_most_common`,
`max_rolls_left`, `upper_below`, `upper_at_least`.
Actions: `keep_values`, `keep_most_common`, `keep_top`, `score_category`,
`score_best`, `score_zero`.

Only one action per rule. Unknown keys are rejected when the file loads, so a
typo cannot silently produce a dead rule.

---

## random — the floor

```json
[{ "cond": { "roll": [1,2,3] }, "action": { "keep_values": [] } },
 { "cond": { "roll": 3 },       "action": { "score_best": true } }]
```

Keeps nothing, re-rolls all five dice twice, then takes whatever pays most.
**111.60.** It is not a "bad strategy" so much as the value of the dice alone:
with no decision-making, five dice and thirteen greedy placements still produce
about 112 points. Everything above this line is the value of the policy.

## chase_yahtzee — one obsession

```json
[{ "cond": { "roll": [1,2], "min_most_common": 2 }, "action": { "keep_most_common": true } },
 { "cond": { "roll": 3, "category_open": "yahtzee" }, "action": { "score_category": "yahtzee" } },
 { "cond": { "roll": 3 },                              "action": { "score_best": true } }]
```

Holds any pair and hopes it becomes five of a kind; scores the Yahtzee box if it
is still open, otherwise falls back to the best value.
**118.53**, with the highest "best single game" of any rule set (828) and the
worst consistency — it is a lottery ticket with a 3.8% Yahtzee-bonus rate and a
bottom score of 40. Chasing 50 points that arrive ~4.6% of the time costs more
than it pays, but it explains why the box is tempting.

## heuristic_benchmark — the obvious compromise

```json
[{ "cond": { "roll": [1,2], "min_most_common": 3 }, "action": { "keep_most_common": true } },
 { "cond": { "roll": [1,2], "min_most_common": 2 }, "action": { "keep_most_common": true } },
 { "cond": { "roll": 3, "category_open": "full_house" }, "action": { "score_category": "full_house" } },
 { "cond": { "roll": 3 },                               "action": { "score_best": true } }]
```

Ambition scaled down: hold three of a kind, then a pair, then take 25 for a full
house when it appears. **130.12.** The improvement over `random` (+18.5) comes
almost entirely from holding pairs; the full-house rule is close to neutral
because a full house usually scores less than the best greedy alternative.

## high_faces — money now

```json
[{ "cond": { "roll": [1,2], "min_count_of_face": { "face": 6, "count": 2 } }, "action": { "keep_values": [6] } },
 { "cond": { "roll": [1,2], "min_count_of_face": { "face": 5, "count": 2 } }, "action": { "keep_values": [5] } },
 { "cond": { "roll": 3, "min_count_of_face": { "face": 6, "count": 3 }, "category_open": "sixes" }, "action": { "score_category": "sixes" } },
 { "cond": { "roll": 3, "min_count_of_face": { "face": 5, "count": 3 }, "category_open": "fives" }, "action": { "score_category": "fives" } },
 { "cond": { "roll": 3, "min_most_common": 3 }, "action": { "keep_most_common": true } },
 { "cond": { "roll": 3 },                       "action": { "score_best": true } }]
```

Holds sixes and fives when there are at least two, scores them when there are at
least three. **138.19** — the best of the simple rule sets, because face value
compounds: sixes are worth 6 apiece *and* push toward the 63-point bonus.

## upper_plan — the best rule set found

Built by searching 72 configurations of the most promising rule family (thresholds
for holding high faces, for scoring them, and for the Yahtzee hold). It is the
ceiling of what this DSL does well.

```json
[{ "cond": { "roll": [1,2], "upper_below": 63, "category_open": "sixes",
             "min_count_of_face": { "face": 6, "count": 1 } }, "action": { "keep_values": [6] } },
 { "cond": { "roll": [1,2], "upper_below": 63, "category_open": "fives",
             "min_count_of_face": { "face": 5, "count": 1 } }, "action": { "keep_values": [5, 6] } },
 { "cond": { "roll": [1,2], "min_most_common": 2 },          "action": { "keep_most_common": true } },
 { "cond": { "roll": 3, "category_open": "yahtzee", "min_most_common": 5 }, "action": { "score_category": "yahtzee" } },
 { "cond": { "roll": 3 },                                    "action": { "score_best": true } }]
```

Shown without the four "score the box when there are 4+ of that face" rules
(sixes, fives, fours, threes), each gated on `upper_below: 55`; the real file is
`examples/strategies.json`.

**156.16**, upper bonus in 5.0% of games. It keeps high faces aggressively while
the bonus is out of reach, then scores boxes only when they are worth at least
four of a kind — an attempt to stop the greedy fallback from polluting the upper
section with junk values.

Reading its rules tells you where it breaks: it has no way to say "this category
is worth more later" or "I am two boxes from 63, so take ones now". Every rule
sees one roll.

## optimal — solved, not written

`simulator/optimal.py` solves the game exactly by dynamic programming. Perfect
play is worth **253.68** (value function: 253.97) — 84 points above the best rule
set, 45% of the total score.

What it does that no rule list here can:

| situation (empty scorecard, roll 1) | optimal keeps | then scores |
|---|---|---|
| 1,2,3,4,6 (four-card straight) | 1,2,3,4 | small straight |
| 2,2,3,3,4 (two pair) | 3,3 | twos |
| 6,6,6,1,2 (three sixes) | 6,6,6 | sixes |
| 1,2,3,5,6 (junk) | 5 | **ones** |
| 4,4,4,4,4 | all five | yahtzee |

With the upper subtotal at 60 instead of 0, the same junk roll keeps `2,3,5`
(chasing the bonus) rather than `5`. The decision changes because the scorecard
changed — that is precisely the axis a first-match rule list cannot represent.

Its upper-bonus rate is 68% against 0.8–5% for the rule sets. The bonus is not
something good rolls deliver; it is a plan from turn one, paid for with cheap
early turns in ones and twos.

---

## Can the optimum be written in that JSON file?

**No.** Not "hard" — impossible for this DSL, and the gap is measurable rather
than a matter of effort.

Three structural reasons:

1. **The decision needs the scorecard, not the dice.** Perfect play needs the
   value of every open category *given* which boxes are filled and how far the
   upper section is from 63. The DSL exposes `upper_below`/`upper_at_least` but
   nothing about which categories are worth what right now, and no arithmetic.
2. **First-match ordering cannot price alternatives.** A rule says "do this",
   not "do this if it beats the alternative by enough". Nearly every optimal move
   is a comparison between two futures: take 30 in sixes now, or take 0 in ones
   to keep sixes for later.
3. **There is no lookahead.** Optimal play trades immediate points for future
   expected points, at a granularity of one roll at a time. A rule list has no
   representation of "expected value of the rest of the game".

The measured ceiling: the family behind `upper_plan` (72 configurations searched,
thresholds for holding/scoring high faces and the Yahtzee hold) topped out at
**157.6** over 3 000 games and **156.16** over 20 000 — 62% of optimal. Adding
the two scorecard conditions above bought roughly 2 points over `high_faces`.

The size of the honest answer: the optimal policy is a table of decisions over
8 128 scorecards × 64 upper-subtotal buckets × 2 Yahtzee-flag values × 252 dice
outcomes — roughly 260 million entries, each an argmax over up to 32 keeps and
13 categories. It is a lookup table, not a paragraph of rules. JSON can hold it
(`simulator.optimal` could dump the tables), but at that point it is data, not a
strategy a human reads or edits — which is why it lives as a solver plus a cache
file instead.

If you want a middle ground, the interesting engineering is to add a real
condition language (`score_if_better_by`, `remaining_categories`, `expected_value`)
and see how close a *readable* policy gets. That is a different project from this
one — and the gap it has to close is the 97 points between `upper_plan` and the
solver, so expect tens of points of shortfall, not a rounding error.
