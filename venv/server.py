# server.py (com integração de planilha)
from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import time
from io import BytesIO

# --------- Configuração Flask/Socket.IO ----------
app = Flask(__name__)
app.config["SECRET_KEY"] = "troque-este-segredo"
socketio = SocketIO(app, cors_allowed_origins="*")

agents = {}   # socket_id -> {"host":"pc-01","last":{...}, "ts":123}
by_host = {}  # host -> socket_id
HISTORY = []  # histórico simples em memória (para export Excel)

# --------- Configuração Google Sheets ----------
# Requer: pip install gspread google-auth
USE_GOOGLE_SHEETS = True   # defina False se não quiser usar Sheets
SHEET_ID = "1NjKNLFDlSQNDvdomSGmiOXix7jaVM6E4PrimbP1DDV8"  # ex: 1AbCdEf... (URL da planilha)
SHEET_WORKSHEET = "Sheet1"  # nome da aba; pode trocar

GSPREAD_CLIENT = None
SHEET = None

if USE_GOOGLE_SHEETS:
    try:
        import gspread  # [11]
        from google.oauth2.service_account import Credentials
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)  # coloque o seu arquivo
        GSPREAD_CLIENT = gspread.authorize(CREDS)  # [11]
        # Abre por ID e seleciona a worksheet
        sh = GSPREAD_CLIENT.open_by_key(SHEET_ID)  # [11]
        SHEET = sh.worksheet(SHEET_WORKSHEET)
        app.logger.info("Google Sheets inicializado com sucesso.")
    except Exception as e:
        app.logger.exception(f"Falha ao inicializar Google Sheets: {e}")
        USE_GOOGLE_SHEETS = False

def sheets_append_snapshot(payload: dict):
    if not (USE_GOOGLE_SHEETS and SHEET):
        return
    # Monte uma linha com colunas estáveis
    row = [
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        payload.get("host"),
        payload.get("idle_seconds"),
        payload.get("user_active"),
        payload.get("foreground_process"),
        payload.get("rocky_running"),
        payload.get("ansys_running"),
        payload.get("rocky_in_focus"),
        payload.get("ansys_in_focus"),
        payload.get("rocky_user_active"),
        payload.get("ansys_user_active"),
        len(payload.get("processes", [])),
    ]
    try:
        # append_row para uma linha, simples e direto [11]
        SHEET.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        app.logger.exception(f"Falha ao escrever no Google Sheets: {e}")

# --------- Endpoint de visão resumida ----------
@app.route("/")
def index():
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
    return jsonify({"status": "ok", "agents": data}), 200  # [13]

# --------- Exportação Excel ----------
# Requer: pip install openpyxl
@app.route("/export.xlsx")
def export_xlsx():
    from openpyxl import Workbook  # [12]
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Telemetry"

    headers = [
        "timestamp","host","idle_seconds","user_active","foreground_process",
        "rocky_running","ansys_running","rocky_in_focus","ansys_in_focus",
        "rocky_user_active","ansys_user_active","process_count"
    ]
    ws.append(headers)

    for rec in HISTORY:
        ws.append([
            rec.get("ts"),
            rec.get("host"),
            rec.get("idle_seconds"),
            rec.get("user_active"),
            rec.get("foreground_process"),
            rec.get("rocky_running"),
            rec.get("ansys_running"),
            rec.get("rocky_in_focus"),
            rec.get("ansys_in_focus"),
            rec.get("rocky_user_active"),
            rec.get("ansys_user_active"),
            len(rec.get("processes", [])),
        ])

    for idx, _ in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = 20

    bio = BytesIO()
    wb.save(bio)  # salvar em memória [12][6]
    bio.seek(0)
    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="telemetry.xlsx",
    )

# --------- Socket.IO Handlers ----------
@socketio.on("connect")
def on_connect():
    emit("hello", {"msg": "connected"})  # [14]

@socketio.on("agent_register")
def on_register(data):
    host = data.get("host", request.sid)
    by_host[host] = request.sid
    agents[request.sid] = {"host": host, "last": None, "ts": time.time()}
    emit("registered", {"host": host})
    socketio.emit("agent_list", {"hosts": list(by_host.keys())})  # broadcast [14]

@socketio.on("agent_snapshot")
def on_snapshot(payload):
    sid = request.sid
    host = agents.get(sid, {}).get("host")
    print("agent_snapshot de", host, "itens:", len(payload.get("processes", [])))

    if sid not in agents:
        return
    agents[sid]["last"] = payload
    agents[sid]["ts"] = time.time()

    # Acumula histórico para export Excel
    HISTORY.append({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        **payload
    })
    # Retenção simples
    if len(HISTORY) > 10000:
        del HISTORY[: len(HISTORY) - 10000]

    # Emite para dashboards
    socketio.emit("telemetry", payload)

    # Escreve no Google Sheets
    sheets_append_snapshot(payload)  # [11][1]

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
