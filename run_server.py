#!/usr/bin/env python3
"""Live view: stream chunk-by-chunk means to viz/realtime.html over websockets."""

from __future__ import annotations

import argparse
import json
import threading

from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from simulator.simulate import load_strategies, simulate_stream

app = Flask(__name__, static_folder="viz")
socketio = SocketIO(app, async_mode="eventlet")


@app.route("/")
def index():
    return send_from_directory("viz", "realtime.html")


def background_simulate(spec_path: str, rounds: int, chunk: int, seed: int) -> None:
    spec = json.loads(open(spec_path, encoding="utf-8").read())
    strategies = load_strategies(spec)
    for chunk_index, snapshot in simulate_stream(strategies, rounds, chunk=chunk, seed=seed):
        socketio.emit("chunk", {"chunk": chunk_index, "snapshot": snapshot})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategies", default="examples/strategies.json")
    parser.add_argument("--rounds", type=int, default=20_000)
    parser.add_argument("--chunk", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    threading.Thread(
        target=background_simulate,
        args=(args.strategies, args.rounds, args.chunk, args.seed),
        daemon=True,
    ).start()
    socketio.run(app, host=args.host, port=args.port)
