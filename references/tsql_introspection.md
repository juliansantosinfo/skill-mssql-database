# Guia de Introspecção T-SQL e Troubleshooting (SQL Server)

Referência modular para descoberta de schema, catálogo interno e diagnóstico operacional no Microsoft SQL Server. Todas as consultas abaixo são seguras para execução com `--read-only`.

---

## 1. Listagem de Tabelas e Contagem Rápida de Linhas (`sys.partitions`)

Evite `SELECT COUNT(*)` em tabelas volumosas (causa *table scan*). Utilize os metadados de `sys.partitions`:

```sql
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.rows) AS approximate_row_count,
    t.create_date,
    t.modify_date
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON t.schema_id = s.schema_id
INNER JOIN sys.partitions AS p
    ON t.object_id = p.object_id
WHERE p.index_id IN (0, 1) -- 0 = Heap, 1 = Clustered Index
GROUP BY s.name, t.name, t.create_date, t.modify_date
ORDER BY approximate_row_count DESC, s.name, t.name;
```

---

## 2. Inspeção de Colunas, Tipos, Nulabilidade e Defaults (`sys.columns`)

```sql
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    c.column_id,
    c.name AS column_name,
    ty.name AS data_type,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable,
    c.is_identity,
    dc.definition AS default_value
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON t.schema_id = s.schema_id
INNER JOIN sys.columns AS c
    ON t.object_id = c.object_id
INNER JOIN sys.types AS ty
    ON c.user_type_id = ty.user_type_id
LEFT JOIN sys.default_constraints AS dc
    ON c.default_object_id = dc.object_id
WHERE s.name = 'dbo'
ORDER BY t.name, c.column_id;
```

---

## 3. Mapeamento de Chaves Estrangeiras (`sys.foreign_keys`)

```sql
SELECT
    fk.name AS fk_name,
    sch_p.name AS parent_schema,
    tbl_p.name AS parent_table,
    col_p.name AS parent_column,
    sch_r.name AS referenced_schema,
    tbl_r.name AS referenced_table,
    col_r.name AS referenced_column,
    fk.delete_referential_action_desc AS on_delete,
    fk.update_referential_action_desc AS on_update
FROM sys.foreign_keys AS fk
INNER JOIN sys.foreign_key_columns AS fkc
    ON fk.object_id = fkc.constraint_object_id
INNER JOIN sys.tables AS tbl_p
    ON fkc.parent_object_id = tbl_p.object_id
INNER JOIN sys.schemas AS sch_p
    ON tbl_p.schema_id = sch_p.schema_id
INNER JOIN sys.columns AS col_p
    ON fkc.parent_object_id = col_p.object_id
   AND fkc.parent_column_id = col_p.column_id
INNER JOIN sys.tables AS tbl_r
    ON fkc.referenced_object_id = tbl_r.object_id
INNER JOIN sys.schemas AS sch_r
    ON tbl_r.schema_id = sch_r.schema_id
INNER JOIN sys.columns AS col_r
    ON fkc.referenced_object_id = col_r.object_id
   AND fkc.referenced_column_id = col_r.column_id
ORDER BY parent_schema, parent_table, fk.name;
```

---

## 4. Inspeção de Índices e Chaves Primárias (`sys.indexes`)

```sql
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    i.name AS index_name,
    i.type_desc AS index_type,
    i.is_primary_key,
    i.is_unique,
    STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS index_columns
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON t.schema_id = s.schema_id
INNER JOIN sys.indexes AS i
    ON t.object_id = i.object_id
INNER JOIN sys.index_columns AS ic
    ON i.object_id = ic.object_id
   AND i.index_id = ic.index_id
INNER JOIN sys.columns AS c
    ON ic.object_id = c.object_id
   AND ic.column_id = c.column_id
WHERE i.type > 0
  AND ic.is_included_column = 0
GROUP BY s.name, t.name, i.name, i.type_desc, i.is_primary_key, i.is_unique
ORDER BY s.name, t.name, i.is_primary_key DESC, i.name;
```

---

## 5. Diagnóstico de Bloqueios e Sessões Ativas (`sys.dm_exec_requests`)

Identifica sessões em execução, esperas de lock (`blocking_session_id`) e o texto SQL correspondente:

```sql
SELECT
    r.session_id,
    r.blocking_session_id,
    r.status,
    r.command,
    r.wait_type,
    r.wait_time AS wait_time_ms,
    r.total_elapsed_time AS elapsed_time_ms,
    s.login_name,
    s.host_name,
    s.program_name,
    DB_NAME(r.database_id) AS database_name,
    SUBSTRING(
        st.text,
        (r.statement_start_offset / 2) + 1,
        (
            (CASE r.statement_end_offset
                WHEN -1 THEN DATALENGTH(st.text)
                ELSE r.statement_end_offset
            END - r.statement_start_offset) / 2
        ) + 1
    ) AS active_statement
FROM sys.dm_exec_requests AS r
INNER JOIN sys.dm_exec_sessions AS s
    ON r.session_id = s.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) AS st
WHERE s.is_user_process = 1
  AND r.session_id <> @@SPID
ORDER BY r.total_elapsed_time DESC;
```

---

## 6. Troubleshooting Rápido — ODBC Driver 18 for SQL Server

| Sintoma / Mensagem de Erro | Causa Provável | Solução Recomendada |
| :--- | :--- | :--- |
| `SSL Provider: [error:0A000086:SSL routines::certificate verify failed:self-signed certificate]` | O **ODBC Driver 18** ativa `Encrypt=yes` por padrão e rejeita certificados autoassinados (padrão em containers Docker e ambientes locais). | Defina `MSSQL_TRUST_SERVER_CERTIFICATE=yes` no arquivo `.env`. |
| `HYT00: [Microsoft][ODBC Driver 18 for SQL Server]Login timeout expired` | Servidor inacessível na rede, porta incorreta, container parado ou firewall bloqueando a porta TCP (padrão `1433`). | 1. Verifique `MSSQL_HOST` e `MSSQL_PORT` no `.env`.<br>2. Use `127.0.0.1` em vez de `localhost` se houver resolução IPv6 lenta.<br>3. Aumente `--timeout 60` na CLI. |
| `IM002` ou `Can't open lib 'ODBC Driver 18 for SQL Server'` | Biblioteca nativa `msodbcsql18` ou `unixODBC` não instalada no sistema operacional. | Solicite autorização ao usuário para instalar o pacote `msodbcsql18` e `unixodbc-dev` no SO. |
| `28000: Login failed for user '...'` | Usuário/senha incorretos ou SQL Server configurado apenas para *Windows Authentication Mode*. | Verifique `MSSQL_USER` e `MSSQL_PASSWORD` no `.env` e confirme que o *Mixed Mode Authentication* está habilitado. |
