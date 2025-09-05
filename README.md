# Idlewatch-Agent-Server

![Versão](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

Um sistema leve de monitoramento em tempo real. É composto por um **agente** em Python que coleta o tempo de inatividade (`idle_time`) e os processos em execução, e um **servidor** Flask-SocketIO que recebe, armazena em memória e transmite esses dados para dashboards ou outros consumidores.

## ✨ Principais Funcionalidades

-   **Monitoramento em Tempo Real**: Visualize o tempo de ociosidade e os processos de uma máquina remotamente.
-   **Agente Leve**: O agente em Python utiliza `psutil` para uma coleta de dados eficiente e com baixo consumo de recursos.
-   **Servidor Centralizado**: O servidor Flask com Socket.IO gerencia múltiplas conexões de agentes e distribui os dados de forma reativa.
-   **Transmissão via WebSockets**: Dados são enviados aos clientes conectados (dashboards) através do evento `telemetry`, garantindo baixa latência.
-   **Endpoints HTTP**: Inclui rotas HTTP para uma rápida verificação do estado do servidor e dos dados coletados.
-   **Fácil de Configurar**: Requer poucas dependências e uma configuração mínima para começar a operar.

## 🚀 Como Funciona

O fluxo de dados é simples e direto, garantindo performance e escalabilidade para pequenos e médios ambientes.

```
+-----------------+      (Envia dados periodicamente)      +----------------------+      (Transmite em tempo real)      +-----------------------+
|                 |--------------------------------------->|                      |------------------------------------->|                       |
|  Agente Python  |                                        |  Servidor Flask-IO   |                                      |  Dashboard / Consumidor |
| (em cada máquina) |<---------------------------------------| (Armazena em memória) |<--------------------------------------|   (Conectado via WS)    |
|                 |      (Comandos/Confirmações)           |                      |       (Solicitações HTTP)            |                       |
+-----------------+                                        +----------------------+                                      +-----------------------+
```

1.  O **Agente** (`agent.py`) é executado na máquina a ser monitorada. Ele coleta o `idle_time` e a lista de processos a cada poucos segundos.
2.  Esses dados são enviados via Socket.IO para o **Servidor** (`server.py`).
3.  O **Servidor** armazena o estado mais recente de cada agente conectado em um dicionário em memória.
4.  Sempre que novos dados chegam, o servidor os transmite através do evento `telemetry` para todos os clientes conectados (como um dashboard web).

## 🔧 Começando

Siga os passos abaixo para configurar e executar o ambiente completo.

### Pré-requisitos

-   Python 3.8 ou superior.
-   `pip` e `venv` (geralmente incluídos com o Python).
-   Para agentes em Linux, é recomendado ter o `xprintidle` para uma medição de ociosidade mais precisa.
    ```bash
    # Debian/Ubuntu
    sudo apt-get install xprintidle
    ```

### 1. Preparando o Ambiente

Primeiro, clone este repositório e crie um ambiente virtual para isolar as dependências.

```bash
git clone https://github.com/rafaelmm16/Idlewatch-Agent-Server.git
cd Idlewatch-Agent-Server
```

**Criar e ativar ambiente virtual:**

-   No Windows:
    ```shell
    python -m venv venv
    venv\Scripts\activate
    ```
-   No Linux ou macOS:
    ```shell
    python3 -m venv venv
    source venv/bin/activate
    ```

### 2. Instalando as Dependências

As dependências são divididas entre o servidor e o agente.

#### Servidor

O servidor precisa do Flask, Flask-SocketIO e, opcionalmente, um servidor WSGI de alta performance como `eventlet` ou `gevent`.

```shell
# Dependências principais
pip install Flask flask-socketio

# Opcional (recomendado para produção, escolha um)
pip install eventlet
# pip install gevent gevent-websocket

# Dependências do Google Sheets
pip install gspread google-auth

pip install openpyxl
```

#### Agente

O agente precisa do cliente Socket.IO e do `psutil` para coletar as métricas.

```shell
# Cliente Socket.IO com todas as dependências de transporte
pip install "python-socketio[client]"

# Biblioteca para coleta de métricas
pip install psutil

# Getting the Active Window Title
pip install pywin32
```

> **Nota:** Instalar `python-socketio[client]` já inclui `requests` e `websocket-client`, prevenindo erros comuns de transporte.

## ⚙️ Uso

Após a instalação, você pode iniciar o servidor e, em seguida, o agente.

### 1. Executar o Servidor

O servidor deve ser iniciado primeiro para que os agentes possam se conectar.

```shell
python server.py
```

> **Importante**: Certifique-se de que no seu `server.py` você está usando `socketio.run(app, ...)` em vez do `app.run(...)` do Flask para que o servidor WebSocket funcione corretamente.
>
> ```python
> # Exemplo em server.py
> if __name__ == '__main__':
>     socketio.run(app, host="0.0.0.0", port=5000, debug=True)
> ```

### 2. Configurar e Executar o Agente

Antes de iniciar o agente, edite o arquivo `agent.py` e ajuste a variável `SERVER_URL` para o endereço IP e porta onde o servidor está sendo executado.

```python
# Em agent.py
SERVER_URL = "http://localhost:5000" # Ou "http://<IP_DO_SERVIDOR>:5000"
```

Agora, execute o agente:

```shell
python agent.py
```

O agente começará a enviar dados para o servidor imediatamente.

## 📡 API e Eventos

A comunicação principal ocorre via Socket.IO, mas o servidor também expõe rotas HTTP.

### Eventos Socket.IO

-   **`telemetry`**: Evento emitido pelo servidor para todos os clientes conectados sempre que um agente envia novos dados.

    **Payload de exemplo:**
    ```json
    {
      "host": "nome-da-maquina",
      "idle_time": 12.34,
      "processes": [
        {"pid": 101, "name": "chrome.exe", "username": "user"},
        {"pid": 102, "name": "code.exe", "username": "user"}
      ]
    }
    ```

### Rotas HTTP

-   **`GET /`**: Rota básica que retorna uma mensagem de status para confirmar que o servidor está online.
-   **`GET /data`**: Retorna um JSON com os dados mais recentes de todos os agentes conectados, útil para debug ou integrações pontuais.
