"""CLI wiring: flags, error messages, JSON output."""

import json
import tempfile
import unittest
from pathlib import Path

from simulator.cli import main
from simulator.simulate import load_strategies


class CliTests(unittest.TestCase):
    def _spec_file(self, tmp: Path) -> Path:
        path = tmp / "strategies.json"
        path.write_text(json.dumps({
            "one": [
                {"cond": {"roll": [1, 2], "min_most_common": 3}, "action": {"keep_most_common": True}},
                {"cond": {"roll": 3}, "action": {"score_best": True}},
            ]
        }))
        return path

    def test_run_writes_json_and_skips_chart(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec = self._spec_file(tmp_path)
            out = tmp_path / "result.json"
            code = main([
                "--strategies", str(spec),
                "--rounds", "200",
                "--chunk", "100",
                "--seed", "1",
                "--json", str(out),
                "--no-viz",
            ])
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text())
        self.assertEqual(payload["meta"]["seed"], 1)
        self.assertEqual(payload["summary"][0]["games"], 200)
        self.assertEqual(len(payload["series"]["one"]), 2)

    def test_run_writes_chart(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec = self._spec_file(tmp_path)
            chart = tmp_path / "chart.html"
            main(["--strategies", str(spec), "--rounds", "100", "--chunk", "50",
                  "--out", str(chart)])
            self.assertTrue(chart.exists())

    def test_missing_strategy_file_errors(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["--strategies", "/nonexistent/strategies.json", "--rounds", "10"])
        self.assertEqual(ctx.exception.code, 2)

    def test_bad_rule_errors_with_config_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "bad.json"
            spec.write_text(json.dumps({"x": [{"cond": {"typo": 1}, "action": {"score_best": True}}]}))
            with self.assertRaises(SystemExit) as ctx:
                main(["--strategies", str(spec), "--rounds", "10", "--no-viz"])
            self.assertEqual(ctx.exception.code, 2)

    def test_zero_rounds_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self._spec_file(Path(tmp))
            with self.assertRaises(SystemExit):
                main(["--strategies", str(spec), "--rounds", "0"])


class ShippedSpecTests(unittest.TestCase):
    def test_example_strategies_load(self):
        spec = json.loads(Path("examples/strategies.json").read_text())
        strategies = load_strategies(spec)
        self.assertGreaterEqual(len(strategies), 3)
        for strategy in strategies:
            self.assertTrue(strategy.rules)


if __name__ == "__main__":
    unittest.main()
