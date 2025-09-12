import subprocess
import threading
import time
import winrm
import json
from datetime import datetime
import gspread
import base64

# --- CONFIGURAÇÃO ---
# CORREÇÃO: Ajustado de "OU-Estacao" para "OU=Estacao"
AD_OU_DN = "OU=CTI,OU=Fixa,OU=Estacao,OU=Campus Sao Mateus,DC=cefetes,DC=br"
ADMIN_USER = 'seu_usuario_admin'
ADMIN_PASSWORD = 'sua_senha_admin'
GOOGLE_SHEET_NAME = "Monitoramento de Laboratórios - CTI"
# --------------------

computer_states = {}

def save_to_google_sheet(computer_states_data):
    """Autentica, limpa e reescreve os dados na Planilha Google com diagnóstico de falhas."""
    try:
        print(f"Autenticando e conectando à planilha '{GOOGLE_SHEET_NAME}'...")
        gc = gspread.service_account(filename="credentials.json")
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.get_worksheet(0)
        print("Conexão bem-sucedida. Limpando a planilha para atualização...")
        worksheet.clear()
        
        headers = [
            "Laboratório", "Máquina", "Status", "Uso de CPU (%)", "Uso de Memória (%)", 
            "Horário da Verificação", "Tempo Ocioso", "Observação"
        ]
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lab_name = AD_OU_DN.split(',')[0].replace('OU=', '')

        rows_to_add = [headers]
        sorted_computers = sorted(computer_states_data.keys())

        for computer_name in sorted_computers:
            data = computer_states_data[computer_name]
            observation_list = []
            
            cpu_usage = data.get('cpu_usage', 'N/A')
            if cpu_usage == 'N/A': observation_list.append("CPU")

            mem_usage = data.get('mem_usage', 'N/A')
            if mem_usage == 'N/A': observation_list.append("Memória")
            
            idle_time = data.get('idle_time')
            if idle_time is None: observation_list.append("Ociosidade")

            status = 'OK' if not observation_list else 'Parcial'
            if not data.get('processes'):
                status = 'Falha na Coleta'
                observation = "Conexão falhou."
            elif observation_list:
                observation = f"Dados indisponíveis: {', '.join(observation_list)}."
            else:
                observation = ''

            idle_time_str = f"{idle_time} min" if isinstance(idle_time, int) else (idle_time or "N/A")
            
            row = [
                lab_name, computer_name, status, str(cpu_usage), str(mem_usage), 
                timestamp, idle_time_str, observation
            ]
            rows_to_add.append(row)
        
        worksheet.update(range_name='A1', values=rows_to_add, value_input_option='USER_ENTERED')
        print(f"Planilha atualizada com os dados de {len(computer_states_data)} máquinas.")

    except Exception as e:
        print(f"ERRO ao tentar enviar dados para o Google Sheets: {e}")

def execute_remote_ps(host, script):
    """Executa scripts PowerShell remotamente usando Base64 para máxima confiabilidade."""
    try:
        full_script = f"$ProgressPreference = 'SilentlyContinue'; {script}"
        encoded_script = base64.b64encode(full_script.encode('utf-16-le')).decode('ascii')
        
        p = winrm.Protocol(endpoint=f'http://{host}:5985/wsman', transport='ntlm', username=ADMIN_USER, password=ADMIN_PASSWORD, server_cert_validation='ignore')
        shell_id = p.open_shell()
        command_id = p.run_command(shell_id, f"powershell.exe -EncodedCommand {encoded_script}")
        std_out, std_err, status_code = p.get_command_output(shell_id, command_id)
        p.close_shell(shell_id)

        if status_code == 0 and std_out:
            return std_out.decode('utf-8', errors='ignore').strip()
        else:
            error_details = std_err.decode('cp850', errors='ignore').strip()
            if error_details and not error_details.startswith('#< CLIXML'):
                print(f"DEBUG: Erro no PowerShell em {host}: {error_details}")
            return None
    except Exception as e:
        print(f"DEBUG: Exceção de conexão em {host}: {e}")
        return None

def get_computers_from_ad(ou_dn):
    print(f"Buscando computadores na OU: {ou_dn}")
    ps_command = f'Import-Module ActiveDirectory; Get-ADComputer -Filter * -SearchBase "{ou_dn}" | Select-Object -ExpandProperty Name'
    try:
        result = subprocess.run(['powershell', '-Command', ps_command], capture_output=True, text=True, check=True)
        return [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
    except Exception as e:
        print(f"ERRO ao buscar computadores no AD: {e}"); return []

def get_remote_processes(host):
    script = "ConvertTo-Json @(Get-Process -IncludeUserName | Select-Object Id, ProcessName, UserName)"
    result = execute_remote_ps(host, script)
    return json.loads(result) if result else []

def get_remote_idle_time(host):
    script = """
    try {
        $session = Get-CimInstance -ClassName Win32_TSSession -ErrorAction Stop | Where-Object { $_.State -eq 'Active' }
        if ($session) { [math]::Floor(($session | Measure-Object -Property IdleTime -Minimum).Minimum / 60000) } 
        else { 'NoActiveSession' }
    } catch { $null }
    """
    result = execute_remote_ps(host, script)
    if result and result.isdigit(): return int(result)
    elif result == 'NoActiveSession': return "Nenhum usuário logado"
    else: return None

def get_remote_cpu_usage(host):
    script = """
    $counter = (Get-Counter -Counter '\\Processor(_Total)\\% Processor Time').CounterSamples.CookedValue
    Start-Sleep -Milliseconds 500
    $counter = (Get-Counter -Counter '\\Processor(_Total)\\% Processor Time').CounterSamples.CookedValue
    [int]$counter
    """
    result = execute_remote_ps(host, script)
    return int(result) if result and result.isdigit() else "N/A"

def get_remote_memory_usage(host):
    script = "[int]((Get-Counter -Counter '\\Memory\\% Committed Bytes In Use').CounterSamples.CookedValue)"
    result = execute_remote_ps(host, script)
    return int(result) if result and result.isdigit() else "N/A"

# Loop principal
def monitor_loop():
    while True:
        target_computers = get_computers_from_ad(AD_OU_DN)
        # Se a lista estiver vazia, pula o resto do loop para evitar erros
        if not target_computers:
            print("Nenhum computador encontrado. Verifique o caminho da OU e a conexão com o AD. Aguardando...")
            time.sleep(60)
            continue

        for computer in target_computers:
            print(f"Coletando dados de {computer}...")
            computer_states[computer] = {
                'processes': get_remote_processes(computer),
                'idle_time': get_remote_idle_time(computer),
                'cpu_usage': get_remote_cpu_usage(computer),
                'mem_usage': get_remote_memory_usage(computer),
            }
        
        save_to_google_sheet(computer_states)
        print("\nAguardando próximo ciclo de monitoramento...")
        time.sleep(60)

if __name__ == '__main__':
    monitor_loop()