---
name: mssql-database
description: Conectar e operar Microsoft SQL Server (MSSQL) local, remoto ou Docker, via arquivo .env e variáveis MSSQL_*, utilizando sqlcmd ou pyodbc para DQL, DML, DDL, inspeção de schemas e confirmação de operações sensíveis. Perguntar quando houver ambiguidade.
compatibility: Linux, Windows e macOS; Python 3.10+; python-dotenv e sqlparse; sqlcmd ODBC do host preferencialmente ou pyodbc + Microsoft ODBC Driver 18.
---

# MSSQL Database — skill base

## Descoberta e credenciais
1. Use **somente um** arquivo `.env`: `--env-file` explícito > `.env` no diretório de execução (`cwd`, raiz do projeto) > `.env` na raiz desta skill. Não percorra diretórios pais nem faça merge entre arquivos. Variáveis já presentes no processo prevalecem sobre o arquivo. A ausência do arquivo não autoriza adivinhar credenciais.
2. Conecte com `MSSQL_HOST`, `MSSQL_PORT` (1433), `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD`; opcionais: `MSSQL_CLIENT=auto|sqlcmd|python`, `MSSQL_SQLCMD_PATH`, `MSSQL_ODBC_DRIVER`, `MSSQL_ENCRYPT`, `MSSQL_TRUST_SERVER_CERTIFICATE`, `MSSQL_COMMAND_TIMEOUT`. Nunca registre credenciais em logs ou respostas.
3. Não confunda `localhost` do host com o de containers; use host/porta acessíveis do ambiente em que o agente executa. Nunca inicie, reinicie ou reconfigure SQL Server/Docker/rede sem autorização.

## Política obrigatória do agente
1. Antes de qualquer operação, confirme o destino por `ping` e identifique banco, ambiente, schema e objetos. Conectividade não significa autorização.
2. Em caso de dúvida sobre destino, campos, filtros, volume, regras de negócio, perda de dados, permissões, transações ou se é produção: **pergunte ao usuário antes de executar alteração**. Não faça suposições nem escolha alvo automaticamente.
3. Antes de escrever, investigue `sys.tables`, `sys.columns`, `sys.indexes`, `sys.foreign_keys`, `INFORMATION_SCHEMA` e dependências. Para DML estime impacto com `SELECT COUNT(*)` e apresente filtros, amostra limitada e plano de rollback. Para DDL analise locks, transações e migrações.
4. **Nunca persista alterações sem aprovação explícita** para o SQL concreto, destino e efeitos. O argumento `--ack confirmed` não substitui aprovação humana. Em produção exija aprovação específica para toda escrita.
5. DDL/DML: por padrão execute `execute` sem `--apply` (prévia transacional com ROLLBACK). Após aprovação use `--apply --ack confirmed`. Prévia não reverte efeitos externos de triggers, chamadas externas ou sequências. Algumas operações não são compatíveis com transação; bloqueie-as no wrapper e use procedimento específico aprovado.
6. `query` destina-se a SELECT/CTE de leitura. A validação lexical é conservadora, mas **não é sandbox de segurança SQL**: funções, views e SQL malicioso podem ter efeitos colaterais. Use conta de privilégios mínimos, especialmente read-only para análise, e revise SQL obtido de entradas não confiáveis.
7. Não execute apenas por ter sido solicitado para **gerar** SQL ou explicar uma solução. Relate resultados reais: servidor/banco, ação, confirmação, linhas quando disponíveis, commit/rollback, limites e testes.
8. **Diagnóstico de dependências e autorização para instalação**:
   - O agente deve verificar os pré-requisitos antes da execução ou caso ocorra erro de conexão/driver:
     - **Pacotes Python**: verificar `python-dotenv`, `sqlparse` e `pyodbc`. Se ausentes, solicitar autorização ao usuário antes de rodar `pip install -r requirements.txt`.
     - **Drivers nativos do SO**: o pacote `pyodbc` do Python necessita do driver nativo instalado no sistema operacional. Verifique os drivers com `python3 -c "import pyodbc; print(pyodbc.drivers())"`. Se o driver configurado (padrão `ODBC Driver 18 for SQL Server`) não estiver presente, ou se `sqlcmd` não estiver no `PATH`, **nunca tente instalar sem consentimento**.
     - **Comunicação e autorização**: informe claramente ao usuário qual dependência de sistema está faltando, apresente os comandos exatos de instalação para a distribuição/sistema detectado (consultando `references/OPERATIONS.md`) e **peça autorização explícita** para executar a instalação ou oriente o usuário a rodar no terminal.
     - **Certificados TLS em containers Docker / Dev**: se a conexão falhar com erro de SSL ou certificado autoassinado (comum em Docker e ambientes locais), oriente o usuário a definir `MSSQL_TRUST_SERVER_CERTIFICATE=yes` no arquivo `.env`.

## Ferramentas locais
- Detecte `sqlcmd` no `PATH` ou via `MSSQL_SQLCMD_PATH`; `MSSQL_CLIENT=auto` prefere `sqlcmd` quando a configuração TLS padrão é compatível, senão `pyodbc`. Nunca instale binários, drivers do SO ou altere o sistema sem autorização explícita do usuário.
- Ao identificar a ausência de `sqlcmd` ou do driver Microsoft ODBC (`msodbcsql18`), informe o usuário, apresente as instruções/comandos apropriados para a plataforma e solicite autorização antes de qualquer instalação.
- `sqlcmd` deve ser a variante ODBC compatível com `-N -b -i -S -U -d`. Existem variantes (como Go sqlcmd) com opções distintas; se for incompatível, selecione `MSSQL_CLIENT=python` e informe a necessidade de pyodbc + driver ODBC. Não desative a verificação TLS em produção sem avaliar risco.
- `sqlcmd` lê a senha de `SQLCMDPASSWORD` **somente no processo filho**; o SQL é enviado por arquivo temporário com permissões restritas e excluído em seguida. A saída desse backend é texto limitado (não JSON estruturado por linha).
- `pyodbc` exige Microsoft ODBC Driver 18 (ou `MSSQL_ODBC_DRIVER` personalizado), mantém senha na memória do processo e fornece saída JSON limitada. Em Linux/macOS o driver depende de instalação de pacote nativo no host (`msodbcsql18`).
- Consulte `references/OPERATIONS.md` para comandos de instalação por sistema operacional e resolução de problemas.

## Interface do executor
```bash
python scripts/mssql_tool.py ping
python scripts/mssql_tool.py query --sql "SELECT TOP (10) name FROM sys.tables"
python scripts/mssql_tool.py execute --file examples/update_example.sql
# Apenas após aprovação inequívoca do usuário:
python scripts/mssql_tool.py execute --file examples/update_example.sql --apply --ack confirmed
# Conexão específica:
python scripts/mssql_tool.py --env-file ./conexoes/producao.env ping
```

## Limites e escalonamento
- Uma instrução SQL por execução, sem `GO`, comandos `EXEC`, gerenciamento explícito de transação ou operações administrativas especiais. `CREATE PROCEDURE`, `CREATE VIEW` complexa, `BACKUP`, `RESTORE`, `CREATE DATABASE`, migrações multi-batch e tarefas envolvendo efeitos externos exigem fluxo especializado.
- Prévia usa ROLLBACK, não simula todos os efeitos/locks e pode causar bloqueios temporários. O wrapper tem limitações de parser e não garante contagem exata de linhas para todo comando ou backend.
- Não imprima dados sensíveis. Para resultados volumosos utilize paginação por query e projeções estritas. Não afirme que um commit foi efetuado se houver erro/timeout: valide estado antes de repetir.
- Skills específicas por sistema ampliam o conhecimento de schema e regras de negócio, sem reduzir controles gerais de autorização e segurança.
