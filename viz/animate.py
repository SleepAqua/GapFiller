"""Animated bar chart of cumulative mean score per strategy.

Plotly is used when it is installed; otherwise a small self-contained HTML page
is written instead, so a machine without plotly still gets the animation.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["build_animation", "has_plotly", "build_fallback_html"]


def has_plotly() -> bool:
    try:
        import plotly.graph_objects  # noqa: F401
    except Exception:
        return False
    return True


def _frames(results: dict[str, list[dict]]) -> list[dict]:
    """Flatten {strategy: [{chunk, cumulative_mean}]} into one list per chunk."""
    by_chunk: dict[int, list[tuple[str, float]]] = {}
    for name, rows in results.items():
        for row in rows:
            by_chunk.setdefault(row["chunk"], []).append((name, row["cumulative_mean"]))
    return [
        {"chunk": chunk, "values": sorted(by_chunk[chunk], key=lambda pair: -pair[1])}
        for chunk in sorted(by_chunk)
    ]


def build_fallback_html(results: dict[str, list[dict]], out_html: str = "results.html") -> str:
    payload = json.dumps(_frames(results), separators=(",", ":"))
    html = _FALLBACK_TEMPLATE.replace("__DATA__", payload)
    target = Path(out_html)
    target.write_text(html, encoding="utf-8")
    return str(target)


def build_animation(results: dict[str, list[dict]], out_html: str = "results.html") -> str:
    """Write the animated chart and return its path."""
    if not has_plotly():
        return build_fallback_html(results, out_html)

    import plotly.graph_objects as go

    frames = _frames(results)
    if not frames:
        raise ValueError("no frames to plot")
    first = frames[0]["values"]
    ceiling = max(value for frame in frames for _, value in frame["values"]) * 1.1

    def bars(values):
        return [
            go.Bar(
                x=[name for name, _ in values],
                y=[value for _, value in values],
                marker_color="#4cc9f0",
                text=[f"{value:.1f}" for _, value in values],
                textposition="outside",
            )
        ]

    figure = go.Figure(
        data=bars(first),
        layout=go.Layout(
            title="Cumulative mean score by strategy",
            yaxis=dict(range=[0, ceiling], title="mean score"),
            template="plotly_dark",
            margin=dict(l=60, r=30, t=60, b=60),
        ),
        frames=[go.Frame(data=bars(frame["values"]), name=str(frame["chunk"])) for frame in frames],
    )
    figure.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                showactive=False,
                y=1.12,
                x=0,
                buttons=[
                    dict(
                        label="Play",
                        method="animate",
                        args=[None, {"frame": {"duration": 120, "redraw": True}, "fromcurrent": True}],
                    )
                ],
            )
        ],
        sliders=[
            dict(
                active=0,
                steps=[
                    dict(
                        method="animate",
                        label=str(frame["chunk"]),
                        args=[[str(frame["chunk"])], {"mode": "immediate", "frame": {"duration": 0}}],
                    )
                    for frame in frames
                ],
                x=0,
                len=0.9,
                currentvalue={"prefix": "chunk: "},
            )
        ],
    )
    # plotly >= 7 drops ``frames`` from write_html, so the page is assembled
    # here: newPlot for the first frame, then addFrames plus a play button.
    payload = json.dumps(figure.to_plotly_json(), separators=(",", ":"))
    html = (_PLOTLY_TEMPLATE
            .replace("__PLOTLYJS__", _plotly_script_tag())
            .replace("__PLOT__", payload))
    target = Path(out_html)
    target.write_text(html, encoding="utf-8")
    return str(target)


def _plotly_script_tag() -> str:
    """Embed plotly so the report opens without a network connection."""
    try:
        from plotly.offline import get_plotlyjs

        return f"<script>{get_plotlyjs()}</script>"
    except Exception:  # pragma: no cover - fall back to the CDN
        return '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'


_PLOTLY_TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<title>Yahtzee strategy comparison</title>
<style>html,body{height:100%;margin:0;background:#111418}</style>
__PLOTLYJS__
<div id="chart" style="width:100%;height:100vh"></div>
<script>
const plot = __PLOT__;
Plotly.newPlot('chart', plot.data, plot.layout, {responsive: true}).then(() => {
  if (plot.frames && plot.frames.length) {
    return Plotly.addFrames('chart', plot.frames);
  }
});
</script>
</html>
"""


_FALLBACK_TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<title>Yahtzee strategy comparison</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; padding: 32px; background: #111418; color: #e8eef5;
         font: 14px/1.4 system-ui, -apple-system, Segoe UI, sans-serif; }
  h1 { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: #8b97a6; margin-bottom: 24px; }
  .row { display: grid; grid-template-columns: 200px 1fr 90px; gap: 12px;
         align-items: center; margin: 10px 0; }
  .name { color: #cfd8e3; text-align: right; }
  .bar { height: 22px; background: #4cc9f0; border-radius: 4px;
         transition: width 180ms ease; }
  .val { color: #9fb0c2; font-variant-numeric: tabular-nums; }
  input[type=range] { width: 100%; margin-top: 24px; }
  .controls { display: flex; gap: 16px; align-items: center; margin-top: 24px; }
  button { background: #1f6f8b; color: #fff; border: 0; padding: 8px 16px;
           border-radius: 6px; cursor: pointer; }
</style>
<h1>Cumulative mean score by strategy</h1>
<div class="sub">Monte Carlo Yahtzee &mdash; one frame per simulated chunk</div>
<div id="chart"></div>
<div class="controls">
  <button id="play">Play</button>
  <span class="val" id="chunk"></span>
</div>
<input type="range" id="slider" min="0" value="0">
<script>
const frames = __DATA__;
const chart = document.getElementById('chart');
const slider = document.getElementById('slider');
slider.max = Math.max(frames.length - 1, 0);
const scale = Math.max(...frames.flatMap(f => f.values.map(v => v[1])), 1);

function render(i) {
  const frame = frames[i];
  chart.innerHTML = frame.values.map(([name, value]) => {
    const width = (value / scale) * 100;
    return '<div class="row"><div class="name">' + name + '</div>' +
           '<div><div class="bar" style="width:' + width.toFixed(2) + '%"></div></div>' +
           '<div class="val">' + value.toFixed(1) + '</div></div>';
  }).join('');
  document.getElementById('chunk').textContent = 'chunk ' + frame.chunk;
  slider.value = i;
}

let timer = null;
document.getElementById('play').onclick = () => {
  if (timer) { clearInterval(timer); timer = null; return; }
  let i = Number(slider.value);
  timer = setInterval(() => {
    i = (i + 1) % frames.length;
    render(i);
  }, 120);
};
slider.oninput = event => render(Number(event.target.value));
render(0);
</script>
</body>
</html>
"""
