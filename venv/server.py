# server.py
from flask import Flask, request
from flask import jsonify
from flask_socketio import SocketIO, emit
from collections import defaultdict
import time

app = Flask(__name__)
app.config["SECRET_KEY"] = "troque-este-segredo"
socketio = SocketIO(app, cors_allowed_origins="*")

agents = {}  # socket_id -> {"host":"pc-01","last":{...}, "ts":123}
by_host = {} # host -> socket_id

@app.route("/")
def index():
    # Monta visão simples: host -> dados resumidos
    data = {}
    for sid, rec in agents.items():
        data[rec["host"]] = {
            "ts": rec["ts"],
            "idle_seconds": (rec["last"] or {}).get("idle_seconds"),
            "user_active": (rec["last"] or {}).get("user_active"),
            "process_count": len((rec["last"] or {}).get("processes", [])),
        }
    return jsonify({"status": "ok", "agents": data}), 200

@socketio.on("connect")
def on_connect():
    emit("hello", {"msg": "connected"})  # handshake simples
    # opcional: exigir token via query string e validar aqui
    # token = request.args.get("token")

@socketio.on("agent_register")
def on_register(data):
    print("agent_register:", data)  # debug
    host = data.get("host", request.sid)
    by_host[host] = request.sid
    agents[request.sid] = {"host": host, "last": None, "ts": time.time()}
    emit("registered", {"host": host})
    socketio.emit("agent_list", {"hosts": list(by_host.keys())})  # broadcast lista atualizada

@socketio.on("agent_snapshot")
def on_snapshot(payload):
    print("agent_snapshot de", agents.get(request.sid, {}).get("host"), "itens:", len(payload.get("processes", [])))
    # payload esperado: {"host": "...", "idle_seconds": 12.3, "user_active": true, "processes": [...]}
    sid = request.sid
    if sid not in agents:
        return
    agents[sid]["last"] = payload
    agents[sid]["ts"] = time.time()
    # Re-emitir para dashboards inscritos
    socketio.emit("telemetry", payload)

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    host = agents.get(sid, {}).get("host")
    agents.pop(sid, None)
    if host and host in by_host:
        by_host.pop(host, None)
    socketio.emit("agent_list", {"hosts": list(by_host.keys())})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
