# mssql-database — Skill para Microsoft SQL Server

Skill Agent Skills com executor multiplataforma **Linux / Windows / macOS**, SQL Server local, remoto ou Docker, DQL/DML/DDL e políticas de confirmação.

## Instalação

1. Copie a pasta para `.agents/skills/mssql-database/` (ou diretório de skills do agente).
2. `python -m pip install -r .agents/skills/mssql-database/requirements.txt`
3. Instale `sqlcmd` ODBC no host **ou** `pyodbc` + Microsoft ODBC Driver 18 (dependência opcional, caso `sqlcmd` não esteja disponível).
4. Crie um `.env` com base em `.env.example` na raiz do **projeto** ou, se ausente, na raiz da **skill**. Não versione credenciais.
5. `python .agents/skills/mssql-database/scripts/mssql_tool.py ping`

## Prioridade do arquivo .env

1. `--env-file ./caminho/arquivo.env` (explícito)
2. `./.env` na raiz de execução do projeto
3. `.env` na raiz da skill

Carrega apenas um arquivo. Variáveis já definidas no processo prevalecem.

## Descoberta de instâncias e geração de .env

Para identificar automaticamente instâncias e databases Microsoft SQL Server no host (instalações locais e containers Docker) e gerar os arquivos `.env` individuais no diretório `./mssql-connections/`, consulte e utilize o prompt em [`prompts/gerar-env-docker.md`](prompts/gerar-env-docker.md).

## Exemplos

```bash
python .agents/skills/mssql-database/scripts/mssql_tool.py query --sql "SELECT TOP (5) name FROM sys.tables"
python .agents/skills/mssql-database/scripts/mssql_tool.py execute --file minha_alteracao.sql
# Com aprovação humana específica:
python .agents/skills/mssql-database/scripts/mssql_tool.py execute --file minha_alteracao.sql --apply --ack confirmed
```

## Atenção

A prévia executa a instrução em transação e faz `ROLLBACK`; ela **não** é inofensiva (locks, gatilhos com efeitos externos etc.). `sqlcmd` e `pyodbc` dependem de ferramentas/drivers existentes no host e acesso TCP. Algumas instruções T-SQL não funcionam em uma transação ou exigem batches (`GO`) e são intencionalmente excluídas. Não foi realizado teste de integração com um SQL Server real. Consulte `SKILL.md` e `references/OPERATIONS.md`.
