import random
import json
import math
from collections import defaultdict
from tqdm import tqdm
from simulator.yahtzee import roll, ALL_CATEGORIES, best_category_score, score_category
from simulator.rules import RuleEngine


class Strategy:
    def __init__(self, name, rules):
        self.name = name
        self.engine = RuleEngine(rules)

    def take_turn(self, open_categories):
        # simulate a single Yahtzee turn (one slot filled)
        dice = roll(5)
        kept_mask = [False]*5
        # up to 2 re-rolls (roll numbers 1..3)
        for roll_num in [1,2,3]:
            state = {'roll': roll_num, 'dice': dice, 'open_categories': set(open_categories)}
            if roll_num < 3:
                keep_mask = self.engine.decide_keep(state)
                # build new dice
                new_dice = []
                for i,keep in enumerate(keep_mask):
                    if keep:
                        new_dice.append(dice[i])
                    else:
                        new_dice.append(random.randint(1,6))
                dice = new_dice
            else:
                # final roll — decide scoring
                score_choice = self.engine.decide_score(state)
                if score_choice and score_choice in open_categories:
                    return score_category(score_choice, dice), score_choice
                # fallback: best available
                best_cat, best_sc = best_category_score(dice, open_categories)
                return best_sc, best_cat


def simulate(strategies, n_games, chunk=10000, seed=None):
    if seed is not None:
        random.seed(seed)
    # strategies: list of Strategy
    results = {s.name: [] for s in strategies}
    chunks = math.ceil(n_games / chunk)
    cumulative = {s.name: 0.0 for s in strategies}
    counts = {s.name: 0 for s in strategies}

    for c in range(chunks):
        to_run = min(chunk, n_games - c*chunk)
        for s in strategies:
            total = 0
            for _ in range(to_run):
                # simulate a full 13-turn game
                open_cats = list(ALL_CATEGORIES)
                game_score = 0
                for _r in range(13):
                    sc, cat = s.take_turn(open_cats)
                    game_score += sc
                    open_cats.remove(cat)
                total += game_score
            cumulative[s.name] += total
            counts[s.name] += to_run
            mean = cumulative[s.name] / counts[s.name]
            results[s.name].append({'chunk': c, 'games_in_chunk': to_run, 'cumulative_mean': mean})
    return results


def simulate_stream(strategies, n_games, chunk=10000, seed=None):
    """
    Generator that yields per-chunk cumulative means for real-time streaming.
    Yields a tuple (chunk_index, snapshot) where snapshot is {strategy: cumulative_mean}
    """
    if seed is not None:
        random.seed(seed)
    chunks = math.ceil(n_games / chunk)
    cumulative = {s.name: 0.0 for s in strategies}
    counts = {s.name: 0 for s in strategies}

    for c in range(chunks):
        to_run = min(chunk, n_games - c*chunk)
        for s in strategies:
            total = 0
            for _ in range(to_run):
                open_cats = list(ALL_CATEGORIES)
                game_score = 0
                for _r in range(13):
                    sc, cat = s.take_turn(open_cats)
                    game_score += sc
                    open_cats.remove(cat)
                total += game_score
            cumulative[s.name] += total
            counts[s.name] += to_run
        snapshot = {name: (cumulative[name] / counts[name]) for name in cumulative}
        yield c, snapshot

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategies', default='examples/strategies.json')
    parser.add_argument('--rounds', type=int, default=10000)
    parser.add_argument('--chunk', type=int, default=1000)
    args = parser.parse_args()
    with open(args.strategies) as f:
        spec = json.load(f)
    strategies = [Strategy(name, rules) for name, rules in spec.items()]
    res = simulate(strategies, args.rounds, chunk=args.chunk)
    import json
    print(json.dumps({k: v[-1] for k,v in res.items()}, indent=2))
