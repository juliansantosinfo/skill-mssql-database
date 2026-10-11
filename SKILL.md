---
name: mssql-database
description: Conectar e operar Microsoft SQL Server (MSSQL) local, remoto ou Docker via pyodbc e arquivo .env no root do projeto. Executa consultas DQL, DML e DDL, inspeciona metadados e orienta na configuração de dependências.
---

# MSSQL Database

Skill leve para conexão e execução direta de comandos SQL no Microsoft SQL Server (local, Docker ou remoto).

## Credenciais e Descoberta (.env)

1. **Localização**: As credenciais são lidas automaticamente do arquivo `.env` localizado na raiz do projeto em execução (`cwd`).
2. **Variáveis obrigatórias**:
   - `MSSQL_HOST`: Endereço do servidor (ex: `127.0.0.1` ou `localhost`).
   - `MSSQL_PORT`: Porta TCP (padrão `1433`).
   - `MSSQL_DATABASE`: Nome do banco de dados.
   - `MSSQL_USER`: Usuário de conexão.
   - `MSSQL_PASSWORD`: Senha do usuário.
3. **Variáveis opcionais**:
   - `MSSQL_ODBC_DRIVER`: Driver ODBC (padrão: `ODBC Driver 18 for SQL Server`).
   - `MSSQL_ENCRYPT`: Criptografia TLS (`yes` ou `no`). Padrão: `yes`.
   - `MSSQL_TRUST_SERVER_CERTIFICATE`: `yes` para aceitar certificados autoassinados (necessário para Docker / dev local). Padrão: `no`.
   - `MSSQL_COMMAND_TIMEOUT`: Timeout da query em segundos (padrão: `30`).
4. **Tratamento de ausência**: Se o `.env` ou chaves obrigatórias não existirem, o executor indicará o erro. **O agente deve perguntar os dados ao usuário** e criar/atualizar o `.env` na raiz do projeto com sua autorização.

## Pré-requisitos e Dependências

- **Python**: `pip install python-dotenv pyodbc`
- **Driver nativo do SO**: O `pyodbc` necessita do driver nativo no sistema operacional (`msodbcsql18`).
  - **Diagnóstico**: Se o driver estiver ausente, o executor retornará mensagem explícita.
  - **Autorização do usuário**: O agente **nunca deve instalar pacotes de sistema silenciosamente**. Deve informar o usuário e pedir autorização para rodar a instalação do driver (ex: no Ubuntu/Debian: `sudo apt-get install -y msodbcsql18 unixodbc-dev`).

## Como Executar

O executor fica em `scripts/mssql_tool.py`:

```bash
# 1. Testar conexão (ping)
python3 scripts/mssql_tool.py --ping

# 2. Executar consulta SQL direta (leitura ou escrita)
python3 scripts/mssql_tool.py --sql "SELECT TOP (10) name FROM sys.tables"

# 3. Executar script a partir de arquivo
python3 scripts/mssql_tool.py --file caminho/para/script.sql

# 4. Ajustar limite de linhas retornadas (padrão: 100)
python3 scripts/mssql_tool.py --sql "SELECT * FROM Clientes" --limit 50
```

## Diretrizes do Agente

1. **Validação inicial**: Sempre execute `--ping` antes de operações complexas para validar conexão, banco e versão.
2. **Aprovação para alterações sensíveis**: Sempre confirme com o usuário antes de rodar comandos destrutivos (`UPDATE`, `DELETE`, `DROP`, `TRUNCATE`). Apresente a query e peça confirmação.
3. **Privacidade de dados**: Nunca exiba senhas ou dados sensíveis nos logs.
