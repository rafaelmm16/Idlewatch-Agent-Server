# agent.py (modificado)
import time, platform, psutil, socketio, subprocess, shutil

SERVER_URL = "http://172.16.231.61:5000"
SOCKETIO_PATH = "/socket.io/"
HOSTNAME = platform.node()

# ----- Configurações específicas -----
IDLE_THRESHOLD_SECONDS = 60  # ajuste conforme necessário
ROCKY_EXEC_NAMES = {"rocky.exe", "rocky"}        # normalizar possíveis nomes
ANSYS_EXEC_NAMES = {"ansys.exe", "ansys", "runwb2.exe", "ansysedt.exe"}  # inclua variantes

# ----- Utilidades de processos -----
def list_processes():
    """Retorna uma lista de todos os processos em execução."""
    procs = []
    for p in psutil.process_iter(attrs=["pid", "name", "status"]):
        try:
            info = p.info
            # Ignora processos sem nome ou com status inválido se desejar
            if info.get("name"):
                procs.append({"pid": info["pid"], "name": info["name"], "status": info["status"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Lida com processos que podem terminar durante a iteração
            continue
    return procs

def is_any_process_running(names: set) -> bool:
    names_lower = {n.lower() for n in names}
    for p in psutil.process_iter(attrs=["name"]):
        try:
            if (p.info.get("name") or "").lower() in names_lower:
                return True
        except Exception:
            continue
    return False

# ----- Idle por SO -----
def get_idle_seconds():
    system = platform.system().lower()
    if system == "windows":
        # GetLastInputInfo (Windows) - API oficial para idle
        import ctypes
        from ctypes import Structure, c_uint, byref, windll, sizeof  # [11]
        class LASTINPUTINFO(Structure):
            _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]
        last = LASTINPUTINFO(); last.cbSize = sizeof(last)
        if windll.user32.GetLastInputInfo(byref(last)) == 0:
            return None
        millis = windll.kernel32.GetTickCount() - last.dwTime
        return millis / 1000.0  # [11]
    elif system == "linux":
        # xprintidle (X11) - simples e prático
        try:
            if shutil.which("xprintidle"):
                idle_time = subprocess.check_output(["xprintidle"], universal_newlines=True)
                return int(idle_time.strip()) / 1000.0  # [6]
            return None
        except Exception:
            return None
    else:
        return None

# ----- Janela em foco -> processo -----
def get_foreground_process_name():
    system = platform.system().lower()
    if system == "windows":
        try:
            import win32gui, win32process  # pywin32
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return psutil.Process(pid).name()  # [1]
        except Exception:
            return None
    elif system == "linux":
        # Tenta via xprop / wmctrl para X11
        try:
            # PID da janela ativa com xprop (EWMH)
            if shutil.which("xprop"):
                root = subprocess.check_output(
                    ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                    universal_newlines=True, stderr=subprocess.DEVNULL
                )
                # linha como: _NET_ACTIVE_WINDOW(WINDOW): window id # 0x04000007
                parts = root.strip().split() 
                win_id = parts[-1] if parts else None
                if not win_id or win_id == "0x0":
                    return None
                prop = subprocess.check_output(
                    ["xprop", "-id", win_id, "_NET_WM_PID"],
                    universal_newlines=True, stderr=subprocess.DEVNULL
                )
                # _NET_WM_PID(CARDINAL) = 12345
                pid = None
                for tok in prop.replace("=", " ").split():
                    if tok.isdigit():
                        pid = int(tok); break
                if pid:
                    return psutil.Process(pid).name()  # [6]
            # Fallback wmctrl -lp (menos confiável)
            if shutil.which("wmctrl"):
                out = subprocess.check_output(["wmctrl", "-lp"], universal_newlines=True)
                # Correlação com janela ativa seria necessária; mantemos xprop prioritário. [6]
            return None
        except Exception:
            return None
    else:
        return None

def snapshot(threshold=IDLE_THRESHOLD_SECONDS):
    idle = get_idle_seconds()
    user_active = (idle is not None and idle < threshold)

    # Estados de Rocky/Ansys
    rocky_running = is_any_process_running(ROCKY_EXEC_NAMES)
    ansys_running = is_any_process_running(ANSYS_EXEC_NAMES)

    fg_name = get_foreground_process_name()
    rocky_in_focus = (fg_name is not None and fg_name.lower() in {n.lower() for n in ROCKY_EXEC_NAMES})
    ansys_in_focus = (fg_name is not None and fg_name.lower() in {n.lower() for n in ANSYS_EXEC_NAMES})

    rocky_user_active = bool(user_active and rocky_in_focus)
    ansys_user_active = bool(user_active and ansys_in_focus)

    # Obter a lista completa de processos
    all_processes = list_processes()

    return {
        "host": HOSTNAME,
        "idle_seconds": idle,
        "user_active": user_active,
        "process_count": len(all_processes), # <-- Adicionamos a contagem total
        "processes": all_processes,          # <-- Agora envia a lista completa
        "rocky_running": rocky_running,
        "ansys_running": ansys_running,
        "rocky_in_focus": rocky_in_focus,
        "ansys_in_focus": ansys_in_focus,
        "rocky_user_active": rocky_user_active,
        "ansys_user_active": ansys_user_active,
        "foreground_process": fg_name,
    }

# ----- Socket.IO -----
sio = socketio.Client(logger=True, engineio_logger=True)

@sio.event
def connect():
    print("Conectado ao servidor")
    sio.emit("agent_register", {"host": HOSTNAME})

@sio.event
def disconnect():
    print("Desconectado do servidor")

def main():
    sio.connect(SERVER_URL, socketio_path=SOCKETIO_PATH)
    try:
        while True:
            if sio.connected:
                sio.emit("agent_snapshot", snapshot())
            time.sleep(5)
    finally:
        sio.disconnect()

if __name__ == "__main__":
    main()
