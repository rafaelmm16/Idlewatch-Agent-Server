# server.py (modificado)
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
app.config["SECRET_KEY"] = "troque-este-segredo"
socketio = SocketIO(app, cors_allowed_origins="*")

agents = {}   # socket_id -> {"host":"pc-01","last":{...}, "ts":123}
by_host = {}  # host -> socket_id

@app.route("/")
def index():
    # Visão simples: host -> dados resumidos (inclui campos Rocky/Ansys)
    data = {}
    for sid, rec in agents.items():
        last = rec.get("last") or {}
        data[rec["host"]] = {
            "ts": rec["ts"],
            "idle_seconds": last.get("idle_seconds"),
            "user_active": last.get("user_active"),
            "process_count": len(last.get("processes", [])),
            "foreground_process": last.get("foreground_process"),
            "rocky_running": last.get("rocky_running"),
            "ansys_running": last.get("ansys_running"),
            "rocky_in_focus": last.get("rocky_in_focus"),
            "ansys_in_focus": last.get("ansys_in_focus"),
            "rocky_user_active": last.get("rocky_user_active"),
            "ansys_user_active": last.get("ansys_user_active"),
        }
    return jsonify({"status": "ok", "agents": data}), 200  # jsonify facilita cabeçalhos e serialização JSON [11]

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
    socketio.emit("agent_list", {"hosts": list(by_host.keys())})  # broadcast para todos [2][5]

@socketio.on("agent_snapshot")
def on_snapshot(payload):
    host = agents.get(request.sid, {}).get("host")
    print("agent_snapshot de", host, "itens:", len(payload.get("processes", [])))
    # payload esperado inclui os novos campos enviados pelo agente
    sid = request.sid
    if sid not in agents:
        return
    agents[sid]["last"] = payload
    agents[sid]["ts"] = time.time()
    # Re-emitir para dashboards inscritos (broadcast implícito fora de contexto) [5]
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
