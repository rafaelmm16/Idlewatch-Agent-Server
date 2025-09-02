# agent.py
import time, platform, psutil, socketio

SERVER_URL = "http://172.16.231.61:5000"
HOSTNAME = platform.node()
SOCKETIO_PATH = "/socket.io/"  # alinhe se o servidor usar outro path

def list_processes(limit=50):
    procs = []
    for p in psutil.process_iter(attrs=["pid","name","status"]):
        try:
            info = p.info
            procs.append({"pid": info["pid"], "name": info["name"], "status": info["status"]})
        except Exception:
            continue
    return procs[:limit]

def get_idle_seconds():
    system = platform.system().lower()
    if system == "windows":
        import ctypes
        from ctypes import Structure, c_uint, byref, windll, sizeof
        class LASTINPUTINFO(Structure):
            _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]
        last = LASTINPUTINFO(); last.cbSize = sizeof(last)
        if windll.user32.GetLastInputInfo(byref(last)) == 0: 
            return None
        millis = windll.kernel32.GetTickCount() - last.dwTime
        return millis / 1000.0
    elif system == "linux":
        try:
            import subprocess
            idle_time = subprocess.check_output(["xprintidle"], universal_newlines=True)
            return int(idle_time.strip()) / 1000.0
        except Exception:
            return None
    else:
        return None

def snapshot(threshold=30):
    idle = get_idle_seconds()
    active = (idle is not None and idle < threshold)
    return {"host": HOSTNAME, "idle_seconds": idle, "user_active": active, "processes": list_processes()}

sio = socketio.Client(logger=True, engineio_logger=True)  # habilitar logs ajuda a depurar [3][4]

@sio.event
def connect():
    print("Conectado ao servidor")
    sio.emit("agent_register", {"host": HOSTNAME})  # emitir após a conexão [4][1]

@sio.event
def disconnect():
    print("Desconectado do servidor")

def main():
    sio.connect("http://172.16.231.61:5000", socketio_path="/socket.io/")  # alinhar path
    try:
        while True:
            if sio.connected:
                sio.emit("agent_snapshot", snapshot())
            time.sleep(5)
    finally:
        sio.disconnect()

if __name__ == "__main__":
    main()
