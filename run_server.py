from flask import Flask, send_from_directory, render_template_string
from flask_socketio import SocketIO
import threading
import json
from simulate import Strategy, simulate_stream

app = Flask(__name__, static_folder='viz')
socketio = SocketIO(app, async_mode='eventlet')

@app.route('/')
def index():
    return send_from_directory('viz', 'realtime.html')

@socketio.on('connect')
def on_connect():
    print('Client connected')

def background_simulate(spec_path='examples/strategies.json', rounds=20000, chunk=2000):
    with open(spec_path) as f:
        spec = json.load(f)
    strategies = [Strategy(name, rules) for name, rules in spec.items()]
    for c, snapshot in simulate_stream(strategies, rounds, chunk=chunk):
        socketio.emit('chunk', {'chunk': c, 'snapshot': snapshot})

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategies', default='examples/strategies.json')
    parser.add_argument('--rounds', type=int, default=20000)
    parser.add_argument('--chunk', type=int, default=2000)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    thread = threading.Thread(target=background_simulate, args=(args.strategies, args.rounds, args.chunk), daemon=True)
    thread.start()
    socketio.run(app, host=args.host, port=args.port)
