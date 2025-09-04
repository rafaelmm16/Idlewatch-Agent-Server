# server.py (com integração de planilha transposta)
from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import time
from io import BytesIO
import logging

# --------- Configuração Flask/Socket.IO ----------
app = Flask(__name__)
app.config["SECRET_KEY"] = "troque-este-segredo"
socketio = SocketIO(app, cors_allowed_origins="*")
logging.basicConfig(level=logging.INFO)


agents = {}  # socket_id -> {"host":"pc-01","last":{...}, "ts":123}
by_host = {}  # host -> socket_id
HISTORY = []  # histórico simples em memória (para export Excel)

# --------- Configuração Google Sheets ----------
# Requer: pip install gspread google-auth
USE_GOOGLE_SHEETS = True  # defina False se não quiser usar Sheets
SHEET_ID = "1NjKNLFDlSQNDvdomSGmiOXix7jaVM6E4PrimbP1DDV8"  # ex: 1AbCdEf... (URL da planilha)
SHEET_WORKSHEET = "Sheet1"  # nome da aba; pode trocar

GSPREAD_CLIENT = None
SHEET = None

# --- NOVA ESTRUTURA PARA GERENCIAR A PLANILHA ---
# Define a ordem fixa das métricas na coluna A
METRIC_ORDER = [
    "timestamp",
    "user_active",
    "foreground_process",
    "rocky_running",
    "ansys_running",
    "process_count",
    # Adicione outras métricas aqui se precisar
]
# Mapeia um hostname para sua respectiva letra de coluna (ex: {"pc-01": "B", "pc-02": "C"})
HOST_COLUMN_MAP = {}


def initialize_google_sheets():
    """
    Inicializa a conexão com o Google Sheets e prepara a estrutura
    com métricas na Coluna A e hosts na Linha 1.
    """
    global GSPREAD_CLIENT, SHEET, HOST_COLUMN_MAP, USE_GOOGLE_SHEETS
    if not USE_GOOGLE_SHEETS:
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from gspread.utils import rowcol_to_a1

        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
        GSPREAD_CLIENT = gspread.authorize(CREDS)
        sh = GSPREAD_CLIENT.open_by_key(SHEET_ID)
        SHEET = sh.worksheet(SHEET_WORKSHEET)
        app.logger.info("Google Sheets inicializado com sucesso.")

        # 1. Verifica se a estrutura base (coluna de métricas) existe
        first_column = SHEET.col_values(1)
        if not first_column or first_column[0] != "Métrica":
            app.logger.info("Planilha vazia ou sem cabeçalho. Configurando estrutura...")
            SHEET.clear()
            # Cria a coluna de cabeçalhos das métricas
            headers_column = [["Métrica"]] + [[metric] for metric in METRIC_ORDER]
            SHEET.update(f"A1:A{len(headers_column)}", headers_column, value_input_option="USER_ENTERED")
            SHEET.format("A1", {"textFormat": {"bold": True}})


        # 2. Mapeia os hosts existentes (colunas) para a memória
        host_row = SHEET.row_values(1) # Pega a primeira linha (onde ficam os hosts)
        for i, host in enumerate(host_row):
            if i > 0 and host: # Pula a coluna A ("Métrica")
                col_letter = rowcol_to_a1(1, i + 1)[:-1] # Converte para letra (ex: 'B')
                HOST_COLUMN_MAP[host] = col_letter

        app.logger.info(f"Hosts mapeados da planilha: {HOST_COLUMN_MAP}")

    except Exception as e:
        app.logger.exception(f"Falha ao inicializar Google Sheets: {e}")
        USE_GOOGLE_SHEETS = False


def sheets_update_host_data(payload: dict):
    """
    Atualiza a coluna de um host específico com os dados mais recentes.
    Se o host for novo, cria uma nova coluna para ele.
    """
    if not (USE_GOOGLE_SHEETS and SHEET):
        return

    host = payload.get("host")
    if not host:
        return

    try:
        # Verifica se o host já tem uma coluna mapeada
        if host not in HOST_COLUMN_MAP:
            from gspread.utils import rowcol_to_a1
            # Host novo, encontrar a próxima coluna livre
            next_col_idx = len(HOST_COLUMN_MAP) + 2  # +2 porque a coluna 1 é de métricas
            col_letter = rowcol_to_a1(1, next_col_idx)[:-1]
            app.logger.info(f"Host '{host}' é novo. Adicionando na coluna {col_letter}.")
            
            # Adiciona o nome do host no cabeçalho (linha 1)
            SHEET.update_cell(1, next_col_idx, host)
            SHEET.format(f"{col_letter}1", {"textFormat": {"bold": True}})

            # Guarda o mapeamento em memória
            HOST_COLUMN_MAP[host] = col_letter

        # Monta a lista de valores na ordem correta definida por METRIC_ORDER
        col_letter = HOST_COLUMN_MAP[host]
        values_to_update = [
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            payload.get("user_active"),
            payload.get("foreground_process"),
            payload.get("rocky_running"),
            payload.get("ansys_running"),
            len(payload.get("processes", [])),
        ]
        
        # Prepara para a API do gspread (lista de listas)
        formatted_values = [[val] for val in values_to_update]

        # Define o range para atualizar (ex: "B2:B7")
        update_range = f"{col_letter}2:{col_letter}{len(formatted_values) + 1}"
        
        # Faz a atualização da coluna
        SHEET.update(update_range, formatted_values, value_input_option="USER_ENTERED")

    except Exception as e:
        app.logger.exception(f"Falha ao escrever no Google Sheets para o host {host}: {e}")

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
    return jsonify({"status": "ok", "agents": data}), 200

# --------- Exportação Excel (Mantida como estava) ----------
# Requer: pip install openpyxl
@app.route("/export.xlsx")
def export_xlsx():
    from openpyxl import Workbook
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
    wb.save(bio)  # salvar em memória
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
    emit("hello", {"msg": "connected"})

@socketio.on("agent_register")
def on_register(data):
    host = data.get("host", request.sid)
    by_host[host] = request.sid
    agents[request.sid] = {"host": host, "last": None, "ts": time.time()}
    emit("registered", {"host": host})
    socketio.emit("agent_list", {"hosts": list(by_host.keys())})

@socketio.on("agent_snapshot")
def on_snapshot(payload):
    sid = request.sid
    host = agents.get(sid, {}).get("host")
    app.logger.info(f"Recebido agent_snapshot de '{host}' com {len(payload.get('processes', []))} processos.")

    if sid not in agents:
        return
    agents[sid]["last"] = payload
    agents[sid]["ts"] = time.time()

    # Acumula histórico para export Excel (formato antigo)
    HISTORY.append({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        **payload
    })
    # Retenção simples
    if len(HISTORY) > 10000:
        del HISTORY[: len(HISTORY) - 10000]

    # Emite para dashboards
    socketio.emit("telemetry", payload)

    # Escreve no Google Sheets com a NOVA LÓGICA
    sheets_update_host_data(payload)

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    host = agents.get(sid, {}).get("host")
    agents.pop(sid, None)
    if host and host in by_host:
        by_host.pop(host, None)
    socketio.emit("agent_list", {"hosts": list(by_host.keys())})

if __name__ == "__main__":
    initialize_google_sheets()
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
