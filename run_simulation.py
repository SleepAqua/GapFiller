import json
from simulate import Strategy, simulate
from viz.animate import build_animation
import argparse

def load_strategies(path):
    with open(path) as f:
        spec = json.load(f)
    return [Strategy(name, rules) for name, rules in spec.items()]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategies', default='examples/strategies.json')
    parser.add_argument('--rounds', type=int, default=10000)
    parser.add_argument('--chunk', type=int, default=1000)
    parser.add_argument('--out', default='results.html')
    args = parser.parse_args()

    strategies = load_strategies(args.strategies)
    res = simulate(strategies, args.rounds, chunk=args.chunk)
    out = build_animation(res, out_html=args.out)
    print('Wrote animation to', out)

if __name__ == '__main__':
    main()
