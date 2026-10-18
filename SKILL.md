---
name: mssql-database
description: Conecta, inspeciona e executa consultas T-SQL (DQL, DML e DDL) em instâncias Microsoft SQL Server (local, Docker ou remota) via pyodbc e arquivo .env. Deve ser ativada quando o agente precisar diagnosticar conectividade, explorar schemas/metadados, consultar dados ou executar scripts SQL em bancos SQL Server.
---

# MSSQL Database Skill

Skill estruturada com *Progressive Disclosure* e *Executable Helpers* para operação segura e determinística de bancos de dados Microsoft SQL Server via [`scripts/mssql_tool.py`](scripts/mssql_tool.py).

## 1. Configuração e Pré-requisitos (`.env`)

As credenciais são lidas automaticamente do arquivo `.env` na raiz do projeto (`cwd`) ou de um caminho informado via `--env-file`:

- **Obrigatórias**: `MSSQL_HOST`, `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD`
- **Opcionais**:
  - `MSSQL_PORT` (padrão: `1433`)
  - `MSSQL_ODBC_DRIVER` (padrão: `ODBC Driver 18 for SQL Server`)
  - `MSSQL_ENCRYPT` (`yes` ou `no`, padrão: `yes`)
  - `MSSQL_TRUST_SERVER_CERTIFICATE` (`yes` para Docker/dev local com certificado autoassinado; padrão: `no`)
  - `MSSQL_COMMAND_TIMEOUT` (timeout em segundos, padrão: `30`)

> **Ação do Agente em Caso de Falha de Ambiente**:
> - **Variáveis/`.env` ausentes (Exit Code `1`)**: Solicite as credenciais ao usuário antes de criar ou atualizar o `.env`.
> - **Driver ODBC ausente (Exit Code `2`)**: Nunca instale pacotes de sistema silenciosamente. Informe o comando adequado (ex.: `sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev`) e peça autorização explícita.

---

## 2. Protocolo Operacional Obrigatório (Passo a Passo)

Todo agente autônomo deve seguir rigorosamente este fluxo em 4 etapas ao interagir com o SQL Server:

### Etapa 1 — Pré-validação de Conectividade (`--ping`)
Antes de qualquer consulta ou diagnóstico, valide a conexão, o banco ativo e a versão do servidor:
```bash
python3 scripts/mssql_tool.py --ping --format json
```

### Etapa 2 — Descoberta de Schema antes de Escrita ou Consultas Complexas
Nunca presuma nomes de tabelas, colunas, tipos ou chaves. Execute a introspecção em modo somente-leitura (`--read-only`):
```bash
python3 scripts/mssql_tool.py --read-only --format json --sql "SELECT s.name AS [schema], t.name AS [table] FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id ORDER BY s.name, t.name"
```
Para consultas avançadas de catálogo (contagem de linhas via `sys.partitions`, índices, FKs e locks), consulte [`references/tsql_introspection.md`](references/tsql_introspection.md).

### Etapa 3 — Execução Segura com Formato Estruturado
- Utilize `--format json` quando o resultado precisar ser interpretado programaticamente pelo agente sem ambiguidade de parsing, ou `--format table` / `--format csv` para visualização humana e exportação.
- Utilize `--read-only` em todas as etapas de diagnóstico e exploração de dados.
```bash
# Consulta exploratória segura em JSON
python3 scripts/mssql_tool.py --read-only --format json --limit 50 --sql "SELECT TOP (50) * FROM dbo.Clientes"

# Execução de script SQL a partir de arquivo com timeout customizado
python3 scripts/mssql_tool.py --file examples/sample_queries.sql --read-only --timeout 60 --format table
```

### Etapa 4 — Validação Pós-Execução
Após qualquer operação de escrita (`INSERT`, `UPDATE`, `DELETE`, `DDL`), verifique o `rowcount` retornado e execute uma consulta de conferência (`--read-only`) para confirmar que o estado final do banco corresponde ao esperado.

---

## 3. Regras de Segurança e Governança

1. **Uso Obrigatório de `TOP (N)`**: Toda consulta exploratória em tabelas de negócio deve limitar explicitamente o volume de dados com `TOP (N)` (além do argumento `--limit` da CLI, padrão `100`) para evitar sobrecarga de memória e I/O.
2. **Bloqueio de Escrita com `--read-only`**: Sempre ative `--read-only` durante investigações, *troubleshooting* e leitura de catálogo. Essa flag bloqueia preventivamente `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE` e `MERGE` (Exit Code `4`).
3. **Transações Explícitas e Aprovação**: Comandos destrutivos ou mutações em lote exigem confirmação prévia do usuário e devem usar blocos transacionais seguros (`BEGIN TRAN` / `BEGIN TRY ... COMMIT TRAN ... END TRY BEGIN CATCH ... ROLLBACK TRAN; THROW; END CATCH`).
4. **Proteção de Segredos**: Nunca exiba senhas em texto puro nos logs, respostas ou comandos versionados.

---

## 4. Referências e Exemplos (Progressive Disclosure)

Mantenha o contexto enxuto carregando os arquivos auxiliares sob demanda:

- **Executor CLI**: [`scripts/mssql_tool.py`](scripts/mssql_tool.py) — Utilitário de linha de comando com suporte a `--ping`, `--sql`, `--file`, `--limit`, `--format` (`table`, `json`, `csv`), `--read-only` e `--timeout`.
- **Introspecção T-SQL & Troubleshooting**: [`references/tsql_introspection.md`](references/tsql_introspection.md) — Consultas otimizadas de catálogo (`sys.partitions`, `sys.columns`, `sys.foreign_keys`, `sys.indexes`, `sys.dm_exec_requests`) e resolução de erros do Driver 18 (`SSL Provider`, `Login timeout`).
- **Exemplos de Consultas**: [`examples/sample_queries.sql`](examples/sample_queries.sql) — Templates seguros de consultas parametrizadas, paginação `OFFSET/FETCH`, transações e inspeção de metadados.
