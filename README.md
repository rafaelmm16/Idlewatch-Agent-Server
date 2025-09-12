# Idlewatch Agent Server

## Descrição

Este projeto consiste em um servidor de monitoramento que coleta dados de computadores em uma unidade organizacional (OU) do Active Directory (AD). O servidor coleta informações como uso de CPU, uso de memória, tempo ocioso e processos em execução. Os dados coletados são então enviados para uma Planilha Google para fácil visualização e análise.


## ✨ Principais Funcionalidades

- **Coleta de Dados Remota:** Utiliza o WinRM para executar scripts PowerShell remotamente e coletar dados das máquinas-alvo.
- **Integração com Active Directory:** Busca automaticamente a lista de computadores a serem monitorados de uma OU específica do AD.
- **Métricas Coletadas:**
    - Uso de CPU (%)
    - Uso de Memória (%)
    - Tempo Ocioso do Usuário (em minutos)
    - Lista de Processos em Execução (ID, Nome do Processo, Usuário)
- **Integração com Google Sheets:** Envia os dados coletados para uma Planilha Google, limpando os dados antigos e inserindo os novos a cada ciclo.
- **Diagnóstico de Falhas:** Identifica e reporta falhas na coleta de dados (e.g., falha de conexão, dados parciais) na própria planilha.
- **Execução Contínua:** Opera em um loop contínuo, atualizando os dados em intervalos definidos (padrão: 60 segundos).

## Pré-requisitos

- Python 3.x
- Acesso de administrador ao servidor onde o script será executado.
- Módulo PowerShell do Active Directory instalado no servidor.
- Credenciais de administrador de domínio para acesso remoto às máquinas.
- WinRM configurado e habilitado nas máquinas-alvo para permitir a execução remota de scripts.
- Uma conta de serviço do Google Cloud com a API do Google Sheets habilitada.

## Configuração

Antes de executar o script, você precisa configurar as seguintes variáveis no arquivo `server.py`:

```python
# --- CONFIGURAÇÃO ---
AD_OU_DN = "OU=Desktops,OU=TI,DC=meudominio,DC=local"
ADMIN_USER = 'seu_usuario_admin'
ADMIN_PASSWORD = 'sua_senha_admin'
GOOGLE_SHEET_NAME = "Monitoramento de Laboratórios - CTI"
```
### Configuração

Antes de executar o script, você precisa configurar as seguintes variáveis no arquivo `server.py`:

- `AD_OU_DN`: O Distinguished Name da Unidade Organizacional do Active Directory onde os computadores a serem monitorados estão localizados.
- `ADMIN_USER`: O nome de usuário de um administrador de domínio com permissões para acessar as máquinas remotamente.
- `ADMIN_PASSWORD`: A senha do administrador de domínio.
- `GOOGLE_SHEET_NAME`: O nome da Planilha Google para onde os dados serão enviados.

### Configuração do Google Sheets

1.  **Crie um projeto no Google Cloud Platform:** Se você ainda não tiver um, crie um novo projeto.
2.  **Ative a API do Google Sheets:** No painel do seu projeto, vá para "APIs e Serviços" > "Biblioteca" e ative a "Google Sheets API".
3.  **Crie uma Conta de Serviço:**
    1.  Vá para "APIs e Serviços" > "Credenciais".
    2.  Clique em "Criar credenciais" e selecione "Conta de serviço".
    3.  Dê um nome à conta de serviço e conceda a ela o papel de "Editor".
    4.  Clique em "Concluir" e, em seguida, na lista de contas de serviço, clique na que você acabou de criar.
    5.  Vá para a aba "Chaves", clique em "Adicionar Chave" > "Criar nova chave".
    6.  Selecione "JSON" como o tipo de chave e o download do arquivo `credentials.json` será iniciado.
4.  **Mova o `credentials.json`:** Coloque o arquivo `credentials.json` no mesmo diretório do `server.py`.
5.  **Compartilhe a Planilha:** Abra a Planilha Google que você especificou em `GOOGLE_SHEET_NAME` e compartilhe-a com o endereço de e-mail da conta de serviço que você criou (encontrado nos detalhes da conta de serviço no Google Cloud Platform).

## Instalação

1.  Clone o repositório:
    ```bash
    git clone [https://github.com/seu-usuario/idlewatch-agent-server.git](https://github.com/seu-usuario/idlewatch-agent-server.git)
    cd idlewatch-agent-server
    ```
2.  Crie e ative um ambiente virtual (recomendado):
    ```bash
    python -m venv venv
    
    # No Windows
    venv\Scripts\activate
    
    # No Linux/macOS
    # source venv/bin/activate
    ```
3.  Instale as dependências:
    ```bash
    pip install gspread pywinrm
    ```

## Uso

Para iniciar o servidor de monitoramento, execute o seguinte comando no terminal:

```bash
python server.py
