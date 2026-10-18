# mssql-database — Skill para Microsoft SQL Server

Skill estruturada para agentes autônomos com *Progressive Disclosure* e *Executable Helpers*, permitindo conexão, introspecção de catálogo e execução segura de comandos T-SQL no Microsoft SQL Server (local, Docker ou remoto) via Python e `pyodbc`.

## Estrutura de Diretórios

```text
mssql-database/
├── SKILL.md                         # Instruções operacionais, protocolo em 4 etapas e regras de segurança
├── README.md                        # Documentação de instalação, arquitetura e uso da CLI
├── requirements.txt                 # Dependências Python (python-dotenv, pyodbc)
├── .env.example                     # Modelo de variáveis de ambiente para conexão
├── scripts/
│   └── mssql_tool.py                # Executor CLI com suporte a --format, --read-only e --timeout
├── references/
│   └── tsql_introspection.md        # Consultas otimizadas de catálogo e troubleshooting do Driver 18
├── examples/
│   └── sample_queries.sql           # Exemplos práticos e seguros de consultas T-SQL
└── tests/
    └── test_mssql_tool.py           # Testes unitários isolados com unittest e unittest.mock
```

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

3. Configure o arquivo `.env` na raiz do seu projeto (baseado em `.env.example`):
   > **Nota para Docker**: Em containers locais com certificado autoassinado, configure `MSSQL_TRUST_SERVER_CERTIFICATE=yes` no `.env`.

## Uso da CLI (`scripts/mssql_tool.py`)

```bash
# 1. Testar conectividade (saída em tabela por padrão ou JSON para agentes):
python3 scripts/mssql_tool.py --ping
python3 scripts/mssql_tool.py --ping --format json

# 2. Executar consulta em modo somente-leitura (--read-only) com saída JSON, tabela ou CSV:
python3 scripts/mssql_tool.py --sql "SELECT TOP (10) name FROM sys.tables" --read-only --format table
python3 scripts/mssql_tool.py --sql "SELECT TOP (10) name FROM sys.tables" --read-only --format json
python3 scripts/mssql_tool.py --sql "SELECT TOP (10) name FROM sys.tables" --read-only --format csv

# 3. Executar script SQL a partir de arquivo com timeout customizado (em segundos):
python3 scripts/mssql_tool.py --file examples/sample_queries.sql --read-only --timeout 60

# 4. Limitar quantidade máxima de linhas retornadas (padrão: 100):
python3 scripts/mssql_tool.py --sql "SELECT * FROM dbo.Clientes" --limit 50 --read-only
```

### Argumentos Suportados

| Argumento | Descrição | Padrão |
| :--- | :--- | :--- |
| `--ping` | Valida a conexão e retorna banco, usuário, servidor e versão. | `False` |
| `--sql <QUERY>` | Instrução T-SQL a ser executada diretamente. | — |
| `--file <PATH>` | Caminho para arquivo `.sql` a ser executado. | — |
| `--format {table,json,csv}` | Formato de saída (`table` para leitura humana, `json` para agentes, `csv` para exportação). | `table` |
| `--read-only` | Bloqueia preventivamente comandos `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE` e `MERGE`. | `False` |
| `--timeout <SEG>` | Timeout de conexão e comando em segundos (sobrescreve `MSSQL_COMMAND_TIMEOUT`). | `30` |
| `--limit <N>` | Limite máximo de linhas buscadas no cursor em consultas `SELECT`. | `100` |
| `--env-file <PATH>` | Caminho customizado para o arquivo `.env`. | `./.env` |

### Códigos de Saída (`sys.exit`)

- `0`: Execução concluída com sucesso.
- `1`: Erro de configuração (`.env` ausente, variáveis obrigatórias faltando ou arquivo `--file` inexistente).
- `2`: Falha de driver ODBC ou erro de conectividade/autenticação/SSL com o SQL Server.
- `3`: Erro de sintaxe T-SQL ou falha na execução da query.
- `4`: Violação de política de segurança (`--read-only`).

## Executando os Testes

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```
