# mssql-database — Skill para Microsoft SQL Server

Skill leve para conexão e execução direta de comandos SQL Server (local, Docker ou remoto) via Python e `pyodbc`.

## Instalação

1. Instale as dependências Python:
   ```bash
   pip install -r requirements.txt
   ```
2. Instale o driver ODBC nativo no sistema operacional (**Microsoft ODBC Driver 18 for SQL Server**):
   - **Ubuntu/Debian**:
     ```bash
     curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
     curl -fsSL https://packages.microsoft.com/config/ubuntu/24.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
     sudo apt-get update
     sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
     ```
   - **macOS**: `brew install msodbcsql18`
   - **Windows**: Baixe e instale o instalador `.msi` oficial da Microsoft.

3. Configure o arquivo `.env` na raiz do seu projeto (veja `.env.example`).
   > **Nota para Docker**: Se o SQL Server estiver em um container local com certificado autoassinado, configure `MSSQL_TRUST_SERVER_CERTIFICATE=yes` no `.env`.

## Uso

```bash
# Testar conectividade:
python3 scripts/mssql_tool.py --ping

# Executar query:
python3 scripts/mssql_tool.py --sql "SELECT TOP (10) name FROM sys.tables"

# Executar a partir de arquivo:
python3 scripts/mssql_tool.py --file script.sql
```
