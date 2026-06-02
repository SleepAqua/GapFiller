Monte Carlo Yahtzee — large-scale strategy simulator

Quick start

- Install dependencies: `pip install -r requirements.txt`
- Run an example (100k games):

```bash
python run_simulation.py --rounds 100000 --chunk 10000 --out results.html
```

This project simulates full Yahtzee scorecards using rule-based strategies. It runs simulations in chunks and produces an animated bar chart (HTML) comparing strategies by cumulative mean score.

Files
- simulator/yahtzee.py — scoring & dice helpers
- simulator/rules.py — simple rule DSL and engine
- simulate.py — core runner (chunked Monte Carlo)
- viz/animate.py — builds Plotly animation from chunked results
- run_simulation.py — CLI wrapper with example strategies
- examples/strategies.json — preset strategies

Notes
- The default strategies include `random`, `chase_yahtzee`, and a small heuristic benchmark.
- Running 1,000,000 full games is expensive; use `--chunk` to control intermediate frame granularity.
