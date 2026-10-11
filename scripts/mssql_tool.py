#!/usr/bin/env python3
"""MSSQL Skill CLI: Executor direto e leve via pyodbc com leitura de .env no root do projeto."""
import argparse
import json
import os
from pathlib import Path
import re
import sys


def load_config(env_file_arg):
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None, "Biblioteca python-dotenv não instalada. Execute: pip install python-dotenv"

    env_path = Path(env_file_arg).expanduser().resolve() if env_file_arg else Path.cwd() / ".env"
    if not env_path.is_file():
        return None, (
            f"Arquivo .env não encontrado em {env_path}. "
            "Crie o arquivo .env no root do projeto com as variáveis de conexão MSSQL_*."
        )

    load_dotenv(env_path, override=True)
    required = ["MSSQL_HOST", "MSSQL_DATABASE", "MSSQL_USER", "MSSQL_PASSWORD"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        return None, (
            f"Variáveis obrigatórias ausentes no {env_path.name}: {', '.join(missing)}. "
            "Solicite as informações ao usuário e configure o .env."
        )

    try:
        port = int(os.getenv("MSSQL_PORT", "1433"))
        timeout = int(os.getenv("MSSQL_COMMAND_TIMEOUT", "30"))
    except ValueError:
        return None, "MSSQL_PORT e MSSQL_COMMAND_TIMEOUT devem ser numéricos."

    return {
        "host": os.environ["MSSQL_HOST"],
        "port": port,
        "db": os.environ["MSSQL_DATABASE"],
        "user": os.environ["MSSQL_USER"],
        "password": os.environ["MSSQL_PASSWORD"],
        "driver": os.getenv("MSSQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
        "encrypt": os.getenv("MSSQL_ENCRYPT", "yes").lower(),
        "trust": os.getenv("MSSQL_TRUST_SERVER_CERTIFICATE", "no").lower(),
        "timeout": timeout,
    }, None


def sanitize_error(err_str, password):
    msg = str(err_str)
    if password:
        msg = msg.replace(password, "******")
    msg = re.sub(r"(?i)(PWD=)[^;]*", r"\1******", msg)
    hint = None
    lower = msg.lower()
    if any(k in lower for k in ("certificate verify failed", "self signed certificate", "ssl provider")):
        hint = "Certificado autoassinado detectado (comum em Docker/Dev local). Defina MSSQL_TRUST_SERVER_CERTIFICATE=yes no .env."
    elif "login failed" in lower:
        hint = "Falha de autenticação. Verifique MSSQL_USER e MSSQL_PASSWORD no .env."
    elif "cannot open database" in lower or "does not exist" in lower:
        hint = "Banco de dados não encontrado ou inacessível no servidor."
    elif any(k in lower for k in ("timeout", "network-related", "connection refused")):
        hint = "Falha de conexão com o servidor. Verifique o host, porta e firewall/rede."
    return msg[:400], hint


def execute(cfg, sql, limit=100, is_ping=False):
    try:
        import pyodbc
    except ImportError:
        return {
            "ok": False,
            "error": "Biblioteca pyodbc não instalada.",
            "hint": "Execute: pip install pyodbc"
        }

    installed = pyodbc.drivers()
    if cfg["driver"] not in installed:
        drivers_fmt = ", ".join(f'"{d}"' for d in installed) if installed else "nenhum"
        return {
            "ok": False,
            "error": f"Driver ODBC \"{cfg['driver']}\" não encontrado no sistema operacional. Drivers instalados: [{drivers_fmt}].",
            "hint": "Instale o driver nativo msodbcsql18 no SO (Ubuntu/Debian: sudo apt-get install -y msodbcsql18)."
        }

    def brace(val):
        return "{" + str(val).replace("}", "}}") + "}"

    host_port = f"tcp:{cfg['host']},{cfg['port']}"
    connstr = ";".join([
        f"DRIVER={brace(cfg['driver'])}",
        f"SERVER={brace(host_port)}",
        f"DATABASE={brace(cfg['db'])}",
        f"UID={brace(cfg['user'])}",
        f"PWD={brace(cfg['password'])}",
        f"Encrypt={cfg['encrypt']}",
        f"TrustServerCertificate={cfg['trust']}",
        "Connection Timeout=10"
    ])

    try:
        with pyodbc.connect(connstr, autocommit=True, timeout=cfg["timeout"]) as cn:
            cursor = cn.cursor()

            if is_ping:
                cursor.execute("SELECT DB_NAME() AS [database], SYSTEM_USER AS [user], @@SERVERNAME AS [server], @@VERSION AS [version]")
                row = cursor.fetchone()
                cols = [c[0] for c in cursor.description]
                return {"ok": True, "ping": dict(zip(cols, row))}

            cursor.execute(sql)
            if cursor.description:
                cols = [c[0] for c in cursor.description]
                fetched = cursor.fetchmany(limit + 1)
                rows = [dict(zip(cols, r)) for r in fetched[:limit]]
                return {
                    "ok": True,
                    "rows": rows,
                    "rowcount": len(rows),
                    "truncated": len(fetched) > limit
                }
            return {
                "ok": True,
                "rowcount": cursor.rowcount
            }
    except pyodbc.Error as e:
        msg, hint = sanitize_error(e, cfg["password"])
        resp = {"ok": False, "error": msg}
        if hint:
            resp["hint"] = hint
        return resp


def main():
    parser = argparse.ArgumentParser(description="Executor leve de comandos SQL Server via pyodbc.")
    parser.add_argument("--env-file", help="Caminho opcional para arquivo .env (padrão: ./.env no root do projeto)")
    parser.add_argument("--sql", help="Instrução SQL a ser executada")
    parser.add_argument("--file", type=Path, help="Arquivo com instrução SQL")
    parser.add_argument("--limit", type=int, default=100, help="Limite máximo de linhas retornadas (padrão: 100)")
    parser.add_argument("--ping", action="store_true", help="Testa conectividade e retorna dados da sessão")

    args = parser.parse_args()

    if not args.ping and not args.sql and not args.file:
        parser.error("Informe --sql, --file ou --ping.")

    cfg, err = load_config(args.env_file)
    if err:
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False))
        return 1

    if args.ping:
        result = execute(cfg, "", is_ping=True)
    else:
        sql = args.sql if args.sql else args.file.read_text(encoding="utf-8-sig")
        result = execute(cfg, sql, limit=args.limit)

    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
