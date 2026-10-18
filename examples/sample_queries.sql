/* ==========================================================================
 * examples/sample_queries.sql
 * Exemplos práticos e seguros de consultas T-SQL para Microsoft SQL Server
 * Compatível com: python3 scripts/mssql_tool.py --file examples/sample_queries.sql --read-only
 * ========================================================================== */

-- 1. Inspeção rápida do ambiente e sessão atual
SELECT
    DB_NAME() AS current_database,
    SYSTEM_USER AS login_user,
    @@SERVERNAME AS server_name,
    SERVERPROPERTY('ProductVersion') AS product_version,
    SERVERPROPERTY('Edition') AS server_edition,
    SYSDATETIMEOFFSET() AS server_timestamp;

-- 2. Resumo das 20 maiores tabelas por número aproximado de linhas (sem lock pesado)
SELECT TOP (20)
    s.name AS schema_name,
    t.name AS table_name,
    SUM(p.rows) AS estimated_rows
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON t.schema_id = s.schema_id
INNER JOIN sys.partitions AS p
    ON t.object_id = p.object_id
WHERE p.index_id IN (0, 1)
GROUP BY s.name, t.name
ORDER BY estimated_rows DESC, s.name, t.name;

-- 3. Exemplo de consulta parametrizada com variáveis T-SQL seguras e paginação OFFSET/FETCH
DECLARE @SchemaFilter NVARCHAR(128) = N'dbo';
DECLARE @PageSize INT = 25;
DECLARE @PageNumber INT = 1;

SELECT
    s.name AS schema_name,
    t.name AS table_name,
    c.column_id,
    c.name AS column_name,
    ty.name AS data_type,
    c.max_length,
    c.is_nullable
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON t.schema_id = s.schema_id
INNER JOIN sys.columns AS c
    ON t.object_id = c.object_id
INNER JOIN sys.types AS ty
    ON c.user_type_id = ty.user_type_id
WHERE s.name = @SchemaFilter
ORDER BY t.name, c.column_id
OFFSET (@PageNumber - 1) * @PageSize ROWS
FETCH NEXT @PageSize ROWS ONLY;
