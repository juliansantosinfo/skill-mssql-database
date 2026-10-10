# Tarefa: Descobrir instâncias e databases Microsoft SQL Server (MSSQL)

Você é um agente de IA especializado em Linux, Docker, Microsoft SQL Server, T-SQL e administração de bancos de dados.

## 1. Objetivo

Identificar todas as instâncias Microsoft SQL Server acessíveis ou configuradas neste host Linux, incluindo instalações locais e containers Docker.

Para cada instância identificada:

1. Descobrir suas configurações de conexão.
2. Identificar os databases existentes.
3. Identificar o usuário utilizado para autenticação.
4. Validar as conexões.
5. Gerar arquivos `.env` compatíveis com a skill `mssql-database`.
6. Apresentar um relatório técnico com os resultados.

**Importante:** executar somente operações de descoberta e leitura. Não modificar bancos de dados, containers, usuários ou configurações.

## 2. Descoberta das instâncias

Utilize as ferramentas disponíveis no host, quando necessário:

- `docker ps -a`
- `docker inspect`
- `docker port`
- `docker compose config`
- `ss -lntp`
- `systemctl`
- `sqlcmd`
- `odbcinst`
- `find` e `which`

Identifique:

- Containers baseados em imagens Microsoft SQL Server.
- Containers com imagens personalizadas contendo SQL Server.
- Instalações nativas do SQL Server.
- Endpoints SQL Server explicitamente configurados em arquivos locais de conexão, respeitando o escopo e as permissões de acesso.

Não faça varreduras indiscriminadas de rede e não altere a configuração dos serviços.

Para cada instância, identifique:

- Nome ou identificador da instância.
- Origem: Docker, local ou servidor remoto.
- Host/IP acessível pelo agente.
- Porta TCP.
- Versão e edição do SQL Server.
- Estado do serviço.
- Usuário de autenticação.
- Método de autenticação.
- Configurações TLS.
- Databases disponíveis.

## 3. Descoberta das credenciais

Investigue configurações já existentes, incluindo:

- Variáveis `MSSQL_SA_PASSWORD` e `SA_PASSWORD`, quando aplicáveis.
- Variáveis de ambiente dos containers.
- Arquivos `.env` relacionados aos projetos.
- Configurações do Docker Compose.
- Arquivos de configuração de conexão já utilizados pelos projetos.

Não presuma que as credenciais de inicialização continuam válidas.

Nunca exiba senhas no terminal, nos logs ou no relatório final.

Não tente adivinhar senhas, redefinir usuários ou contornar mecanismos de autenticação.

Caso não seja possível identificar uma credencial válida, solicite ao usuário a configuração necessária.

Evite imprimir o conteúdo completo de arquivos e configurações que possam conter segredos.

## 4. Identificação dos databases

Para cada instância na qual a autenticação for bem-sucedida, execute consultas somente leitura.

Identifique a versão:

```sql
SELECT
    @@SERVERNAME AS server_name,
    @@VERSION AS server_version,
    SERVERPROPERTY('Edition') AS edition;
```

Liste os databases visíveis ao usuário:

```sql
SELECT
    name,
    database_id,
    state_desc,
    recovery_model_desc,
    compatibility_level,
    create_date
FROM sys.databases
ORDER BY name;
```

Considere que a visibilidade dos databases depende das permissões da conta utilizada.

Classifique os databases como:

- Sistema: `master`, `model`, `msdb`, `tempdb`.
- Usuário: databases de aplicações e projetos.

Priorize os databases de usuário para a geração dos arquivos `.env`.

Não tente acessar databases sem autorização.

## 5. Geração dos arquivos .env

Crie o diretório:

`./mssql-connections/`

Gere um arquivo `.env` para cada database de usuário identificado e acessível.

O nome deverá seguir o padrão:

`<instancia>__<database>.env`

Exemplo:

```text
mssql-connections/
├── sqlserver-erp__ERP_PRODUCAO.env
├── sqlserver-erp__ERP_HOMOLOG.env
├── sqlserver-dev__APP_DEV.env
└── sqlserver-dev__APP_TEST.env
```

Sanitize os nomes para impedir caracteres inseguros, colisões e caminhos inválidos.

Cada arquivo deverá seguir o padrão da skill `mssql-database`:

```dotenv
# Conexão SQL Server
MSSQL_HOST=127.0.0.1
MSSQL_PORT=1433
MSSQL_DATABASE=nome_database
MSSQL_USER=usuario
MSSQL_PASSWORD=senha

# Cliente
MSSQL_CLIENT=auto
MSSQL_ODBC_DRIVER=ODBC Driver 18 for SQL Server

# Segurança
MSSQL_ENCRYPT=yes
MSSQL_TRUST_SERVER_CERTIFICATE=no
MSSQL_COMMAND_TIMEOUT=30
```

Regras:

1. Usar o endereço acessível a partir do host Linux.
2. Para Docker, utilizar a porta publicada no host, quando disponível.
3. Não presumir que a porta externa é 1433.
4. Preservar a configuração TLS necessária para uma conexão segura.
5. Não utilizar `MSSQL_TRUST_SERVER_CERTIFICATE=yes` automaticamente para contornar erros de certificado.
6. Não sobrescrever arquivos existentes sem autorização.
7. Não criar arquivos com credenciais ausentes ou inventadas.
8. Se houver autenticação integrada incompatível com o formato atual da skill, informar a limitação antes de gerar o arquivo.
9. Definir permissão `600` para cada arquivo criado.
10. Garantir que o diretório de conexões esteja ignorado pelo Git.
11. Não incluir bancos de sistema, salvo solicitação explícita.

## 6. Validação das conexões

Após gerar cada arquivo, valide a conexão utilizando preferencialmente a skill `mssql-database`.

Exemplo:

```bash
python scripts/mssql_tool.py \
  --env-file ./mssql-connections/instancia__database.env \
  ping
```

Se a skill não estiver disponível, utilize `sqlcmd` ou outro cliente SQL Server já instalado no host.

Execute uma consulta de validação:

```sql
SELECT
    DB_NAME() AS database_name,
    SYSTEM_USER AS connected_user,
    @@SERVERNAME AS server_name;
```

Confirme que `DB_NAME()` corresponde ao database configurado no arquivo.

Não execute DDL ou DML.

Não instale pacotes ou drivers sem autorização.

Não permita que comandos de diagnóstico imprimam credenciais ou strings de conexão com senhas.

## 7. Relatório final

Apresente duas tabelas.

**Tabela 1 — Instâncias identificadas**

- Instância
- Origem
- Container, quando aplicável
- Host
- Porta
- Versão SQL Server
- Edição
- Situação da conexão

**Tabela 2 — Databases identificados**

- Instância
- Database
- Tipo: sistema ou usuário
- Status
- Usuário utilizado
- Caminho do arquivo `.env`
- Resultado da validação

Não exibir senhas.

Apresente também os problemas encontrados, suas possíveis causas e as ações necessárias para resolvê-los.

## 8. Regras obrigatórias de comportamento

- Nunca interromper ou reiniciar containers.
- Nunca modificar configurações Docker.
- Nunca alterar usuários ou senhas.
- Nunca criar ou excluir databases.
- Nunca executar comandos DDL ou DML.
- Nunca modificar redes, portas ou firewalls.
- Nunca expor credenciais nos logs ou relatórios.
- Nunca assumir configurações sem evidências.
- Nunca sobrescrever arquivos existentes sem aprovação.
- Sempre solicitar esclarecimentos quando houver dúvidas sobre instâncias, databases, credenciais ou configurações.
- Reutilizar ferramentas e dependências já disponíveis no host.
- Priorizar operações não invasivas.

## 9. Critério de conclusão

A tarefa será considerada concluída quando:

1. As instâncias identificáveis tiverem sido inventariadas.
2. Os databases visíveis e acessíveis tiverem sido catalogados.
3. Os arquivos `.env` dos databases de usuário tiverem sido gerados.
4. Cada arquivo tiver sido validado por conexão real.
5. As credenciais estiverem protegidas.
6. O relatório final tiver sido apresentado.

Caso alguma etapa não seja possível, informe a limitação e solicite as informações necessárias. Não apresente uma conexão não validada como funcional.

Comece verificando as ferramentas disponíveis no host e identificando as instâncias SQL Server existentes.
