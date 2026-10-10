# Operação e segurança

## Variáveis
- Obrigatórias: `MSSQL_HOST`, `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD`.
- Opcionais: `MSSQL_PORT=1433`, `MSSQL_CLIENT=auto`, `MSSQL_SQLCMD_PATH`, `MSSQL_ODBC_DRIVER=ODBC Driver 18 for SQL Server`, `MSSQL_ENCRYPT=yes`, `MSSQL_TRUST_SERVER_CERTIFICATE=no`, `MSSQL_COMMAND_TIMEOUT=30` (segundos).
- A senha nunca deve ir na linha de comando. `.env` deve ficar fora do controle de versão; Linux/macOS: `chmod 600 .env`; Windows: restringir ACL da pasta/arquivo.
- `MSSQL_ENCRYPT=yes` usa criptografia, com validação da cadeia de certificados no backend pyodbc. Em sqlcmd a opção `-N` exige criptografia, mas as opções TLS variam entre versões de `sqlcmd`. Use `MSSQL_CLIENT=python` caso a política exija modo TLS alternativo. Não habilite `MSSQL_TRUST_SERVER_CERTIFICATE=yes` sem avaliar risco de MITM.

## Execução Linux/macOS
```bash
python3 -m pip install -r /caminho/da/skill/requirements.txt
python3 /caminho/da/skill/scripts/mssql_tool.py ping
python3 /caminho/da/skill/scripts/mssql_tool.py query --sql 'SELECT TOP (10) name FROM sys.tables'
python3 /caminho/da/skill/scripts/mssql_tool.py --env-file ./conexoes/teste.env ping
```

## Execução Windows PowerShell
```powershell
py -3 -m pip install -r .agents/skills/mssql-database/requirements.txt
py -3 .agents/skills/mssql-database/scripts/mssql_tool.py ping
py -3 .agents/skills/mssql-database/scripts/mssql_tool.py query --sql "SELECT TOP (10) name FROM sys.tables"
```

## Docker / rede
Se o agente roda no host e o container publica `15433:1433`, utilize `MSSQL_HOST=127.0.0.1`, `MSSQL_PORT=15433`. Se o agente roda em outro container na mesma rede Docker, `MSSQL_HOST=nome-do-servico`, `MSSQL_PORT=1433`. Conexões a servidores remotos dependem de TCP/IP, firewall e TLS; a skill não muda a infraestrutura.

## Inspeção SQL segura
```sql
SELECT TOP (50) TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```
```sql
SELECT c.name, t.name AS data_type, c.max_length, c.is_nullable
FROM sys.columns AS c
JOIN sys.types AS t ON t.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.Clientes');
```

## Restrições
O parser não é uma fronteira de segurança. Mantenha credenciais read-only para consultas e credenciais restritas para escrita; nunca utilize `sa` por padrão. O backend sqlcmd entrega texto truncado; pyodbc oferece JSON limitado a 100 linhas (máximo 1000). Para SQL com parâmetros, prefira scripts especializados com placeholders e revisão antes de executar.
