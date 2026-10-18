#!/usr/bin/env python3
"""MSSQL Skill CLI: Executor estruturado e seguro para SQL Server via pyodbc e .env."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Optional, Sequence, Union

try:
    import pyodbc  # type: ignore[import-not-found]
except ImportError:
    pyodbc = None  # type: ignore[assignment]

# Códigos de saída semânticos
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_CONNECTION_ERROR = 2
EXIT_SQL_ERROR = 3
EXIT_READ_ONLY_ERROR = 4

READ_ONLY_FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "MERGE",
)

_READ_ONLY_PATTERN = re.compile(
    r"\b(" + "|".join(READ_ONLY_FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


class ConfigError(ValueError):
    """Erro de configuração ou variáveis de ambiente ausentes/inválidas."""

    def __init__(self, message: str, hint: Optional[str] = None) -> None:
        super().__init__(message)
        self.hint = hint or (
            "Verifique o arquivo .env na raiz do projeto e defina MSSQL_HOST, "
            "MSSQL_DATABASE, MSSQL_USER e MSSQL_PASSWORD."
        )


class ReadOnlyError(PermissionError):
    """Violação de segurança quando um comando de escrita é executado com --read-only."""

    def __init__(self, message: str, keyword: Optional[str] = None) -> None:
        super().__init__(message)
        self.keyword = keyword
        self.hint = (
            "Operação bloqueada pelo modo --read-only. Remova a flag --read-only "
            "após confirmar a operação com o usuário."
        )


def _get_pyodbc() -> Any:
    """Obtém a referência ativa do módulo pyodbc (permite mock via sys.modules ou atributo)."""
    if pyodbc is not None:
        return pyodbc
    mod = sys.modules.get("pyodbc")
    if mod is not None:
        return mod
    try:
        import pyodbc as _pyodbc  # type: ignore[import-not-found]

        return _pyodbc
    except ImportError:
        return None


def _fallback_load_dotenv(env_path: Path) -> None:
    """Carrega variáveis de um arquivo .env caso python-dotenv não esteja disponível."""
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            os.environ[key] = value


def load_db_config(
    env_file: Optional[Union[str, Path]] = None,
    timeout_override: Optional[int] = None,
) -> dict[str, Any]:
    """Carrega e valida a configuração de conexão do banco a partir do arquivo .env.

    Args:
        env_file: Caminho opcional para o arquivo .env (padrão: ./.env no diretório atual).
        timeout_override: Sobrescreve o timeout de comando (em segundos), se informado.

    Returns:
        Dicionário contendo parâmetros validados de conexão.

    Raises:
        ConfigError: Se o arquivo .env não existir, variáveis obrigatórias estiverem
            ausentes ou valores numéricos forem inválidos.
    """
    env_path = Path(env_file).expanduser().resolve() if env_file else Path.cwd() / ".env"
    if not env_path.is_file():
        raise ConfigError(
            f"Arquivo .env não encontrado em {env_path}. "
            "Crie o arquivo .env no root do projeto com as variáveis de conexão MSSQL_*."
        )

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        _fallback_load_dotenv(env_path)

    required = ["MSSQL_HOST", "MSSQL_DATABASE", "MSSQL_USER", "MSSQL_PASSWORD"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise ConfigError(
            f"Variáveis obrigatórias ausentes no {env_path.name}: {', '.join(missing)}. "
            "Solicite as informações ao usuário e configure o .env."
        )

    try:
        port = int(os.getenv("MSSQL_PORT", "1433"))
        timeout = (
            int(timeout_override)
            if timeout_override is not None
            else int(os.getenv("MSSQL_COMMAND_TIMEOUT", "30"))
        )
    except ValueError as exc:
        raise ConfigError(
            "MSSQL_PORT, MSSQL_COMMAND_TIMEOUT e --timeout devem ser valores numéricos inteiros."
        ) from exc

    if port <= 0 or port > 65535:
        raise ConfigError(f"Porta inválida ({port}). MSSQL_PORT deve estar entre 1 e 65535.")
    if timeout <= 0:
        raise ConfigError(f"Timeout inválido ({timeout}). O timeout deve ser maior que zero.")

    db_name = os.environ["MSSQL_DATABASE"]
    return {
        "host": os.environ["MSSQL_HOST"],
        "port": port,
        "db": db_name,
        "database": db_name,
        "user": os.environ["MSSQL_USER"],
        "password": os.environ["MSSQL_PASSWORD"],
        "driver": os.getenv("MSSQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
        "encrypt": os.getenv("MSSQL_ENCRYPT", "yes").lower(),
        "trust": os.getenv("MSSQL_TRUST_SERVER_CERTIFICATE", "no").lower(),
        "timeout": timeout,
    }


def load_config(
    env_file_arg: Optional[Union[str, Path]] = None,
    timeout_override: Optional[int] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Wrapper retrocompatível que retorna (cfg, erro_str)."""
    try:
        return load_db_config(env_file=env_file_arg, timeout_override=timeout_override), None
    except ConfigError as exc:
        return None, str(exc)


def build_connection_string(cfg: dict[str, Any]) -> str:
    """Constrói a connection string ODBC segura para o Microsoft SQL Server.

    Args:
        cfg: Dicionário de configuração retornado por `load_db_config`.

    Returns:
        String de conexão ODBC formatada com escape de chaves.
    """

    def brace(val: Any) -> str:
        return "{" + str(val).replace("}", "}}") + "}"

    host = cfg["host"]
    port = cfg.get("port", 1433)
    database = cfg.get("db") or cfg.get("database", "")
    user = cfg["user"]
    password = cfg["password"]
    driver = cfg.get("driver", "ODBC Driver 18 for SQL Server")
    encrypt = cfg.get("encrypt", "yes")
    trust = cfg.get("trust", "no")
    conn_timeout = int(cfg.get("timeout", 30))

    host_port = f"tcp:{host},{port}"
    return ";".join(
        [
            f"DRIVER={brace(driver)}",
            f"SERVER={brace(host_port)}",
            f"DATABASE={brace(database)}",
            f"UID={brace(user)}",
            f"PWD={brace(password)}",
            f"Encrypt={encrypt}",
            f"TrustServerCertificate={trust}",
            f"Connection Timeout={conn_timeout}",
        ]
    )


def _strip_sql_comments_and_literals(sql: str) -> str:
    """Remove comentários e literais de texto/identificadores para análise léxica segura."""
    pattern = re.compile(
        r"('(?:''|[^'])*')|(\"(?:\"\"|[^\"])*\")|(\[[^\]]*\])|(--[^\r\n]*)|(/\*[\s\S]*?\*/)"
    )
    return pattern.sub(" ", sql)


def validate_read_only(sql: str) -> None:
    """Valida se a instrução SQL não contém comandos de escrita/DDL proibidos em modo read-only.

    Args:
        sql: Consulta T-SQL a ser inspecionada.

    Raises:
        ReadOnlyError: Se um comando destrutivo ou de modificação for detectado.
    """
    cleaned = _strip_sql_comments_and_literals(sql)
    match = _READ_ONLY_PATTERN.search(cleaned)
    if match:
        keyword = match.group(1).upper()
        raise ReadOnlyError(
            f"Comando '{keyword}' bloqueado: execução em modo somente-leitura (--read-only).",
            keyword=keyword,
        )


def sanitize_error(err: Any, password: Optional[str] = None) -> tuple[str, Optional[str], str, int]:
    """Sanitiza mensagens de erro ocultando senhas e classifica a falha.

    Returns:
        Tupla (mensagem_limpa, hint, error_type, exit_code).
    """
    msg = str(err)
    if password:
        msg = msg.replace(password, "******")
    msg = re.sub(r"(?i)(PWD=)[^;]*", r"\1******", msg)

    lower = msg.lower()
    hint: Optional[str] = None
    error_type = "sql_error"
    exit_code = EXIT_SQL_ERROR

    if any(
        k in lower
        for k in (
            "data source name not found",
            "can't open lib",
            "file not found",
            "driver",
            "im002",
        )
    ) and any(k in lower for k in ("odbc", "driver", "im002", "can't open lib")):
        error_type = "driver_error"
        exit_code = EXIT_CONNECTION_ERROR
        hint = (
            "Verifique se o Microsoft ODBC Driver 18 for SQL Server (msodbcsql18) "
            "está instalado no sistema operacional."
        )
    elif any(
        k in lower
        for k in ("certificate verify failed", "self signed certificate", "ssl provider")
    ):
        error_type = "connection_error"
        exit_code = EXIT_CONNECTION_ERROR
        hint = (
            "Certificado autoassinado detectado (comum em Docker/Dev local). "
            "Defina MSSQL_TRUST_SERVER_CERTIFICATE=yes no .env."
        )
    elif "login failed" in lower:
        error_type = "connection_error"
        exit_code = EXIT_CONNECTION_ERROR
        hint = "Falha de autenticação. Verifique MSSQL_USER e MSSQL_PASSWORD no .env."
    elif "cannot open database" in lower:
        error_type = "connection_error"
        exit_code = EXIT_CONNECTION_ERROR
        hint = "Banco de dados não encontrado ou usuário sem permissão de acesso."
    elif any(
        k in lower
        for k in (
            "login timeout",
            "timeout expired",
            "network-related",
            "connection refused",
            "server is not found",
            "unable to connect",
            "08001",
            "hyt00",
        )
    ):
        error_type = "connection_error"
        exit_code = EXIT_CONNECTION_ERROR
        hint = (
            "Falha de conexão ou timeout com o servidor. Verifique MSSQL_HOST, "
            "MSSQL_PORT, firewall ou aumente --timeout."
        )
    else:
        error_type = "sql_error"
        exit_code = EXIT_SQL_ERROR
        hint = "Erro de sintaxe T-SQL ou objeto inexistente. Revise a query e consulte o schema antes de executar."

    return msg[:400], hint, error_type, exit_code


def _check_odbc_driver(pyodbc_mod: Any, driver_name: str) -> Optional[dict[str, Any]]:
    """Verifica disponibilidade do driver ODBC quando pyodbc.drivers() lista drivers instalados."""
    drivers_fn = getattr(pyodbc_mod, "drivers", None)
    if not callable(drivers_fn):
        return None
    try:
        installed = drivers_fn()
    except Exception:
        return None

    if isinstance(installed, (list, tuple)) and driver_name not in installed:
        drivers_fmt = ", ".join(f'"{d}"' for d in installed) if installed else "nenhum"
        return {
            "ok": False,
            "error_type": "driver_error",
            "error": (
                f'Driver ODBC "{driver_name}" não encontrado no sistema operacional. '
                f"Drivers instalados: [{drivers_fmt}]."
            ),
            "hint": (
                "Instale o driver nativo msodbcsql18 no SO "
                "(Ubuntu/Debian: sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev)."
            ),
            "exit_code": EXIT_CONNECTION_ERROR,
        }
    return None


def ping_server(cfg: dict[str, Any], timeout: Optional[int] = None) -> dict[str, Any]:
    """Testa a conectividade com o SQL Server e retorna metadados básicos da sessão.

    Args:
        cfg: Dicionário de configuração de conexão.
        timeout: Timeout opcional em segundos para a operação.

    Returns:
        Dicionário estruturado com o status da conexão e dados do servidor.
    """
    pyodbc_mod = _get_pyodbc()
    if pyodbc_mod is None:
        return {
            "ok": False,
            "error_type": "driver_error",
            "error": "Biblioteca pyodbc não instalada.",
            "hint": "Execute: pip install pyodbc",
            "exit_code": EXIT_CONNECTION_ERROR,
        }

    effective_cfg = dict(cfg)
    if timeout is not None:
        effective_cfg["timeout"] = int(timeout)

    connstr = build_connection_string(effective_cfg)
    effective_timeout = int(effective_cfg.get("timeout", 30))
    db_err_cls = getattr(pyodbc_mod, "Error", Exception)

    try:
        with pyodbc_mod.connect(connstr, autocommit=True, timeout=effective_timeout) as cn:
            if hasattr(cn, "timeout"):
                cn.timeout = effective_timeout
            cursor = cn.cursor()
            cursor.execute(
                "SELECT DB_NAME() AS [database], SYSTEM_USER AS [user], "
                "@@SERVERNAME AS [server], @@VERSION AS [version]"
            )
            row = cursor.fetchone()
            cols = [c[0] for c in cursor.description] if cursor.description else []
            ping_data = dict(zip(cols, row)) if row and cols else {}
            return {
                "ok": True,
                "ping": ping_data,
                "exit_code": EXIT_SUCCESS,
            }
    except db_err_cls as exc:
        driver_check = _check_odbc_driver(
            pyodbc_mod, effective_cfg.get("driver", "ODBC Driver 18 for SQL Server")
        )
        if driver_check is not None:
            return driver_check
        msg, hint, error_type, exit_code = sanitize_error(exc, effective_cfg.get("password"))
        if error_type == "sql_error":
            error_type = "connection_error"
            exit_code = EXIT_CONNECTION_ERROR
        resp: dict[str, Any] = {
            "ok": False,
            "error_type": error_type,
            "error": msg,
            "exit_code": exit_code,
        }
        if hint:
            resp["hint"] = hint
        return resp


def execute_sql(
    cfg: dict[str, Any],
    sql: str,
    limit: int = 100,
    read_only: bool = False,
    timeout: Optional[int] = None,
) -> dict[str, Any]:
    """Executa uma instrução T-SQL no SQL Server com controle de limite, timeout e read-only.

    Args:
        cfg: Dicionário de configuração de conexão.
        sql: Instrução T-SQL a ser executada.
        limit: Limite máximo de linhas retornadas em consultas DQL (padrão: 100).
        read_only: Se True, bloqueia comandos de escrita ou alteração de schema.
        timeout: Timeout opcional em segundos para a execução.

    Returns:
        Dicionário estruturado contendo `ok`, `rows`/`rowcount`/`columns` ou detalhes de erro.
    """
    if not sql or not sql.strip():
        return {
            "ok": False,
            "error_type": "sql_error",
            "error": "A instrução SQL fornecida está vazia.",
            "hint": "Informe uma consulta T-SQL válida via --sql ou --file.",
            "exit_code": EXIT_SQL_ERROR,
        }

    if read_only:
        try:
            validate_read_only(sql)
        except ReadOnlyError as exc:
            return {
                "ok": False,
                "error_type": "security_error",
                "error": str(exc),
                "hint": exc.hint,
                "exit_code": EXIT_READ_ONLY_ERROR,
            }

    pyodbc_mod = _get_pyodbc()
    if pyodbc_mod is None:
        return {
            "ok": False,
            "error_type": "driver_error",
            "error": "Biblioteca pyodbc não instalada.",
            "hint": "Execute: pip install pyodbc",
            "exit_code": EXIT_CONNECTION_ERROR,
        }

    effective_cfg = dict(cfg)
    if timeout is not None:
        effective_cfg["timeout"] = int(timeout)

    connstr = build_connection_string(effective_cfg)
    effective_timeout = int(effective_cfg.get("timeout", 30))
    db_err_cls = getattr(pyodbc_mod, "Error", Exception)

    try:
        with pyodbc_mod.connect(connstr, autocommit=True, timeout=effective_timeout) as cn:
            if hasattr(cn, "timeout"):
                cn.timeout = effective_timeout
            cursor = cn.cursor()
            cursor.execute(sql)
            if cursor.description:
                cols = [c[0] for c in cursor.description]
                fetched = cursor.fetchmany(limit + 1)
                rows = [dict(zip(cols, r)) for r in fetched[:limit]]
                return {
                    "ok": True,
                    "columns": cols,
                    "rows": rows,
                    "rowcount": len(rows),
                    "truncated": len(fetched) > limit,
                    "exit_code": EXIT_SUCCESS,
                }
            return {
                "ok": True,
                "rowcount": cursor.rowcount,
                "exit_code": EXIT_SUCCESS,
            }
    except db_err_cls as exc:
        driver_check = _check_odbc_driver(
            pyodbc_mod, effective_cfg.get("driver", "ODBC Driver 18 for SQL Server")
        )
        if driver_check is not None:
            return driver_check
        msg, hint, error_type, exit_code = sanitize_error(exc, effective_cfg.get("password"))
        resp: dict[str, Any] = {
            "ok": False,
            "error_type": error_type,
            "error": msg,
            "exit_code": exit_code,
        }
        if hint:
            resp["hint"] = hint
        return resp


def execute(
    cfg: dict[str, Any],
    sql: str,
    limit: int = 100,
    is_ping: bool = False,
    read_only: bool = False,
    timeout: Optional[int] = None,
) -> dict[str, Any]:
    """Wrapper retrocompatível que delega para `ping_server` ou `execute_sql`."""
    if is_ping:
        return ping_server(cfg, timeout=timeout)
    return execute_sql(cfg, sql, limit=limit, read_only=read_only, timeout=timeout)


def _render_ascii_table(columns: Sequence[str], rows: Sequence[dict[str, Any]]) -> str:
    """Renderiza uma tabela ASCII alinhada a partir de colunas e linhas."""
    if not columns:
        return "(sem colunas)"

    str_rows = [["" if r.get(col) is None else str(r.get(col)) for col in columns] for r in rows]
    widths = [len(str(col)) for col in columns]
    for srow in str_rows:
        for idx, cell in enumerate(srow):
            first_line = cell.splitlines()[0] if cell else ""
            if len(first_line) > widths[idx]:
                widths[idx] = len(first_line)

    header = " | ".join(str(col).ljust(widths[idx]) for idx, col in enumerate(columns))
    separator = "-+-".join("-" * widths[idx] for idx in range(len(columns)))
    lines = [header, separator]
    for srow in str_rows:
        formatted_cells = []
        for idx, cell in enumerate(srow):
            clean_cell = " ".join(cell.splitlines()) if cell else ""
            formatted_cells.append(clean_cell.ljust(widths[idx]))
        lines.append(" | ".join(formatted_cells))
    return "\n".join(lines)


def format_output(result: dict[str, Any], fmt: str = "table") -> str:
    """Formata o dicionário de resultado no formato solicitado (`table`, `json` ou `csv`).

    Args:
        result: Dicionário retornado por `ping_server` ou `execute_sql`.
        fmt: Formato de saída desejado (`table`, `json` ou `csv`). Padrão: `table`.

    Returns:
        String formatada pronta para exibição em stdout.

    Raises:
        ValueError: Se o formato especificado não for suportado.
    """
    normalized_fmt = fmt.lower().strip()
    if normalized_fmt not in ("table", "json", "csv"):
        raise ValueError(f"Formato inválido '{fmt}'. Use 'table', 'json' ou 'csv'.")

    payload = {k: v for k, v in result.items() if k != "exit_code"}

    if normalized_fmt == "json":
        return json.dumps(payload, ensure_ascii=False, default=str)

    if not payload.get("ok"):
        err_type = payload.get("error_type", "error")
        err_msg = payload.get("error", "Erro desconhecido.")
        hint = payload.get("hint")
        if normalized_fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            writer.writerow(["ok", "error_type", "error", "hint"])
            writer.writerow([False, err_type, err_msg, hint or ""])
            return buf.getvalue().rstrip("\n")
        lines = [f"[ERRO ({err_type})] {err_msg}"]
        if hint:
            lines.append(f"Dica: {hint}")
        return "\n".join(lines)

    if "ping" in payload:
        ping_info: dict[str, Any] = payload["ping"]
        cols = list(ping_info.keys())
        if normalized_fmt == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
            writer.writeheader()
            writer.writerow({k: str(v) for k, v in ping_info.items()})
            return buf.getvalue().rstrip("\n")
        return _render_ascii_table(cols, [ping_info])

    if "rows" in payload:
        rows: list[dict[str, Any]] = payload["rows"]
        cols = payload.get("columns") or (list(rows[0].keys()) if rows else [])
        if normalized_fmt == "csv":
            buf = io.StringIO()
            if cols:
                writer = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: ("" if row.get(k) is None else str(row.get(k))) for k in cols})
            return buf.getvalue().rstrip("\n")

        table_str = _render_ascii_table(cols, rows) if cols else "(0 linhas)"
        rowcount = payload.get("rowcount", len(rows))
        trunc_note = " [truncado]" if payload.get("truncated") else ""
        return f"{table_str}\n({rowcount} linha(s) retornada(s){trunc_note})"

    rowcount = payload.get("rowcount", 0)
    if normalized_fmt == "csv":
        return f"rowcount\n{rowcount}"
    return f"Comando executado com sucesso. Linhas afetadas: {rowcount}"


def build_parser() -> argparse.ArgumentParser:
    """Constrói e retorna o parser de argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Executor estruturado e seguro de comandos SQL Server via pyodbc."
    )
    parser.add_argument(
        "--env-file",
        help="Caminho opcional para arquivo .env (padrão: ./.env no root do projeto)",
    )
    parser.add_argument("--sql", help="Instrução SQL a ser executada")
    parser.add_argument("--file", type=Path, help="Arquivo contendo instrução SQL")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limite máximo de linhas retornadas em consultas (padrão: 100)",
    )
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Testa conectividade e retorna dados da sessão",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        help="Formato de saída dos resultados: table, json ou csv (padrão: table)",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Bloqueia comandos de escrita/DDL (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout de conexão e execução em segundos (sobrescreve MSSQL_COMMAND_TIMEOUT)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Ponto de entrada principal da CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.ping and not args.sql and not args.file:
        parser.error("Informe --sql, --file ou --ping.")

    try:
        cfg = load_db_config(env_file=args.env_file, timeout_override=args.timeout)
    except ConfigError as exc:
        err_result = {
            "ok": False,
            "error_type": "config_error",
            "error": str(exc),
            "hint": exc.hint,
            "exit_code": EXIT_CONFIG_ERROR,
        }
        print(format_output(err_result, args.format))
        return EXIT_CONFIG_ERROR

    if args.ping:
        result = ping_server(cfg, timeout=args.timeout)
    else:
        if args.sql:
            sql = args.sql
        else:
            file_path: Path = args.file.expanduser().resolve()
            if not file_path.is_file():
                file_err = {
                    "ok": False,
                    "error_type": "config_error",
                    "error": f"Arquivo SQL não encontrado em {file_path}.",
                    "hint": "Verifique o caminho informado no argumento --file.",
                    "exit_code": EXIT_CONFIG_ERROR,
                }
                print(format_output(file_err, args.format))
                return EXIT_CONFIG_ERROR
            sql = file_path.read_text(encoding="utf-8-sig")

        result = execute_sql(
            cfg,
            sql,
            limit=args.limit,
            read_only=args.read_only,
            timeout=args.timeout,
        )

    print(format_output(result, args.format))
    if result.get("ok"):
        return EXIT_SUCCESS
    return int(result.get("exit_code", EXIT_SQL_ERROR))


if __name__ == "__main__":
    sys.exit(main())
