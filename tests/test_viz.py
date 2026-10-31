"""Chart generation, with and without plotly."""

import json
import tempfile
import unittest
from pathlib import Path

from viz.animate import build_animation, build_fallback_html, has_plotly

SERIES = {
    "alpha": [{"chunk": 0, "games_in_chunk": 10, "cumulative_mean": 100.0},
              {"chunk": 1, "games_in_chunk": 10, "cumulative_mean": 105.0}],
    "beta": [{"chunk": 0, "games_in_chunk": 10, "cumulative_mean": 90.0},
             {"chunk": 1, "games_in_chunk": 10, "cumulative_mean": 95.0}],
}


class FallbackTests(unittest.TestCase):
    def test_fallback_html_embeds_frames_and_ends_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chart.html"
            build_fallback_html(SERIES, str(target))
            html = target.read_text()
        self.assertIn("const frames = [", html)
        self.assertIn("alpha", html)
        self.assertIn("</html>", html)
        self.assertEqual(html.count("<script>"), html.count("</script>"))

    def test_frames_are_ordered_and_ranked(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chart.html"
            build_fallback_html(SERIES, str(target))
            html = target.read_text()
        payload = html.split("const frames = ", 1)[1].split(";", 1)[0]
        frames = json.loads(payload)
        self.assertEqual([f["chunk"] for f in frames], [0, 1])
        self.assertEqual([name for name, _ in frames[0]["values"]], ["alpha", "beta"])


class PlotlyTests(unittest.TestCase):
    @unittest.skipUnless(has_plotly(), "plotly not installed")
    def test_plotly_page_contains_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chart.html"
            build_animation(SERIES, out_html=str(target))
            html = target.read_text()
        self.assertIn("Plotly.newPlot", html)
        self.assertIn("addFrames", html)
        # plotly >= 7 drops frames from write_html; the page must still carry them
        self.assertIn('"frames"', html)
        self.assertIn("alpha", html)

    def test_build_animation_works_without_plotly(self):
        # Whichever backend is available, the file must exist and be HTML.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chart.html"
            build_animation(SERIES, out_html=str(target))
            self.assertTrue(target.exists())
            self.assertIn("<html", target.read_text().lower().replace("<!doctype html>", "<html"))


if __name__ == "__main__":
    unittest.main()
