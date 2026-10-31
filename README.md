# Monte Carlo Yahtzee — strategy simulator

Play hundreds of thousands of full Yahtzee games against each other and compare
scorecards, instead of debating which strategy "feels" better over a kitchen
table.

```
strategy                 games     mean     se  upper%  best  worst
-------------------------------------------------------------------
high_faces              20,000   138.19   0.28    0.8%   498     37
heuristic_benchmark     20,000   130.12   0.41    1.7%   693     39
chase_yahtzee           20,000   118.53   0.27    3.8%   828     40
random                  20,000   111.60   0.20    0.0%   343     31
```

(`./run.sh --rounds 20000 --workers 4`, i7-7700HQ.)

## Quick start

```bash
cd ~/coding/GapFiller

./run.sh --rounds 20000 --chunk 2000            # table + results.html chart
./run.sh --rounds 20000 --optimal               # include solved optimal play
./run.sh --rounds 1000000 --chunk 10000 --workers 8 --no-viz
./run.sh test                                   # 54 unit tests
```

`./run.sh` pins the interpreter to `/home/louis/.venvs/main/bin/python`; override
with `PYTHON=/path/to/python`. Bare `python` on this machine can resolve to a
different venv without numpy.

Dependencies: `numpy` (fast dice), `plotly` (chart, optional — a plain-HTML
fallback is written if it is missing), `flask` + `flask-socketio` (live view
only). See `requirements.txt`.

## What it does

- 13-turn games under standard rules, with the **upper-section bonus** (63 points
  → +35) and the **100-point Yahtzee bonus** for extra Yahtzees once the Yahtzee
  box holds 50.
- Strategies are JSON rule lists (see below); a strategy decides what to keep on
  rolls 1–2 and where to score on roll 3, falling back to the best immediate
  value when no rule applies.
- Results stream back as cumulative means per chunk, which is what the animated
  chart plays back.

## The optimal strategy

Yahtzee's best play is known: solitaire Yahtzee was solved exactly, and perfect
play is worth **254.587729** points per game under Hasbro rules with the forced
joker (Verhoeff; reproduced by the reference solvers). No rule list can reach it,
because the right move depends on the whole scorecard, not on the dice alone.

So this project solves the game instead of imitating it:
`simulator/optimal.py` runs a dynamic program over

    state = (scored categories, upper subtotal capped at 63, Yahtzee box holds 50, dice)

with all 252 dice outcomes and all 462 keeps enumerated exactly — no sampling.
That is 8128 masks x 64 subtotal buckets x 2 flags, solved in one pass; the value
function is cached to `data/optimal_values.npz` (a solve takes 4-8 minutes,
once; `python -m simulator.optimal --force` rebuilds it).

Result for **this engine's ruleset**: perfect play is worth **253.97** points.
A 20 000-game run of the solved policy measures **253.68 ± 0.41**, so the value
function and the replay agree.

| strategy | mean | se | upper bonus | best | worst |
|---|---|---|---|---|---|
| **optimal (solved)** | **253.68** | 0.41 | **68.1%** | 672 | 90 |
| upper_plan | 156.16 | 0.40 | 5.0% | 657 | 49 |
| high_faces | 138.19 | 0.28 | 0.8% | 498 | 37 |
| heuristic_benchmark | 130.12 | 0.41 | 1.7% | 693 | 39 |
| chase_yahtzee | 118.53 | 0.27 | 3.8% | 828 | 40 |
| random | 111.60 | 0.20 | 0.0% | 343 | 31 |

Three things that fall out of this:

- The best hand-written rule set in this repo (`upper_plan`, found by searching
  72 configurations) is worth **97 points less** than perfect play — 38% of the
  total. Greedy rules leave most of the game on the table.
- Optimal play earns the upper bonus in **68%** of games; every rule strategy
  here manages 0–4%. The bonus is not a side effect of good rolls, it is a plan.
- The published 254.59 is 0.62 above this engine's 253.97 because that ruleset
  pays joker values (25/30/40) for a Yahtzee placed in full house / small / large
  straight, which this engine scores as 0. The gap is the missing rule, not an
  error in the solver.

## CLI

| flag | meaning |
|---|---|
| `--rounds` | games per strategy (default 10 000) |
| `--chunk` | games per reported point / chart frame (default 1 000) |
| `--seed` | seed for the whole run (default 0) |
| `--workers` | processes; `0` means all cores |
| `--strategies` | JSON file of rules (default `examples/strategies.json`) |
| `--out` | animated chart path (default `results.html`, ~4.7 MB: plotly JS is embedded so it opens offline) |
| `--no-viz` | skip the chart |
| `--optimal` | add the solved optimal policy to the comparison |
| `--json` | write `{meta, summary, series}` for further analysis |

## Determinism and fairness

Two properties the tests enforce:

- **Reproducible.** Each block of games is seeded from `(seed, block index)` only,
  so a run is identical regardless of `--workers`. Ties in category choice break
  in a fixed canonical order — never by set iteration order, which is randomised
  per process and silently made earlier versions disagree between serial and
  parallel runs.
- **Common random numbers.** Every die for a block is drawn up front
  (`games × 195` values) and every strategy consumes the same stream, so a
  10-point gap between strategies is strategy, not luck.

## Performance

Dice are pre-drawn into a byte buffer, per-roll face counts are computed once, and
all thirteen category scores come from a single pass over the roll:

| | games/s |
|---|---|
| first working version (pre-refine) | ~3 600 |
| this version, 1 core | 5 400 – 7 500 (block size dependent) |
| this version, 8 cores | ~26 800 |

1 000 000 games × 4 strategies ≈ 2.5 minutes on this laptop. Memory stays flat:
workers return counters, not games.

## Layout

```
simulator/
  yahtzee.py   scoring, upper bonus, fast all-category scoring, dice rows
  rules.py     rule DSL: conditions, actions, validation, compiled predicates
  game.py      one 13-turn game, dice from an iterator
  simulate.py  block seeding, process pool, aggregation, streaming
  optimal.py   exact dynamic-programming solver + replayable policy
  cli.py       argument parsing, table output, JSON export
viz/animate.py plotly chart, with a self-contained HTML fallback
tests/         54 unit tests: scoring, DSL, determinism, aggregation, CLI, chart,
               and the optimal solver/replay agreement
docs/STRATEGIES.md  every strategy explained, plus the DSL-vs-optimal gap
examples/strategies.json
```

## Writing a strategy

A strategy is a list of rules; the first matching rule wins.

```json
{"cond": {"roll": [1, 2], "min_count_of_face": {"face": 6, "count": 2}},
 "action": {"keep_values": [6]}}
```

Conditions: `roll`, `category_open`, `min_count_of_face`, `min_most_common`,
`max_rolls_left`, `upper_below`, `upper_at_least`. Actions: `keep_values`,
`keep_most_common`, `keep_top`, `score_category`, `score_best`, `score_zero`.

Unknown keys raise at load time — a typo fails loudly instead of producing a rule
that never fires.

## Rules modelled, and what is not

Modelled: thirteen categories, upper bonus, Yahtzee bonus, best-value fallback,
deliberate zero placement via `score_zero`.

Not modelled: the official "Joker" placement rules for a Yahtzee rolled after the
Yahtzee box is used (the roll simply scores wherever the strategy sends it), and
scratch/zero strategy is up to the rule author.

A finding worth knowing: rule-based policies almost never earn the upper bonus
(0.8–5% of games here), because reaching 63 means spending early turns on ones and
twos and a first-match rule list has no way to price that trade. The solved
policy takes it in 68% of games. The bonus is a plan, not a side effect.

Every strategy, its rules and what it scores: **`docs/STRATEGIES.md`** — including
a measured answer to "can the optimal strategy just be written as JSON?" (no:
the best of 72 rule configurations reaches 156.16, 62% of optimal).

## Live view

```bash
./run.sh serve --rounds 20000 --chunk 2000
# then open http://<this-host>:5000
```

Streams chunk-by-chunk means over a websocket to `viz/realtime.html`.

## Android app

`android_app/` is an independent Kotlin reimplementation of the simulator
(coroutines, one strategy per chunk) and is not built by this Python project. The
Gradle distribution and build output are no longer tracked in git; run
`./gradlew` inside `android_app/` if you want the APK.
