#!/usr/bin/env python3
"""MSSQL skill CLI: sqlcmd from host or pyodbc, with project/skill .env fallback."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def load_env(explicit):
    try:
        from dotenv import load_dotenv
    except ImportError as e:
        raise ValueError('Instale python-dotenv: python -m pip install -r requirements.txt') from e
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Arquivo --env-file não encontrado')
    else:
        project = Path.cwd() / '.env'
        path = project if project.is_file() else ROOT / '.env'
    if path.is_file():
        load_dotenv(path, override=False)
    return path if path.is_file() else None


def conf():
    names = ('MSSQL_HOST', 'MSSQL_DATABASE', 'MSSQL_USER', 'MSSQL_PASSWORD')
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise ValueError('Variáveis ausentes: ' + ', '.join(missing))
    port = int(os.getenv('MSSQL_PORT', '1433'))
    timeout = int(os.getenv('MSSQL_COMMAND_TIMEOUT', '30'))
    if not 1 <= port <= 65535 or not 1 <= timeout <= 300:
        raise ValueError('Porta ou timeout fora do intervalo permitido')
    encrypt = os.getenv('MSSQL_ENCRYPT', 'yes').lower()
    trust = os.getenv('MSSQL_TRUST_SERVER_CERTIFICATE', 'no').lower()
    if encrypt not in ('yes', 'no', 'mandatory', 'optional', 'strict') or trust not in ('yes', 'no'):
        raise ValueError('MSSQL_ENCRYPT ou MSSQL_TRUST_SERVER_CERTIFICATE inválido')
    return {'host': os.environ['MSSQL_HOST'], 'port': port, 'db': os.environ['MSSQL_DATABASE'],
            'user': os.environ['MSSQL_USER'], 'password': os.environ['MSSQL_PASSWORD'],
            'timeout': timeout, 'encrypt': encrypt, 'trust': trust}


def statement(sql, action):
    try:
        import sqlparse
    except ImportError as e:
        raise ValueError('Instale sqlparse: python -m pip install -r requirements.txt') from e
    stmts = sqlparse.parse(sql)
    meaningful = [s for s in stmts if str(s).strip(' \r\n\t;')]
    if len(meaningful) != 1:
        raise ValueError('Apenas uma instrução SQL por chamada')
    s = str(meaningful[0]).strip().rstrip(';')
    # sqlcmd GO is a batch separator; never accept it inside user statements.
    if re.search(r'(?im)^\s*GO(?:\s+\d+)?\s*$', s):
        raise ValueError('GO / múltiplos batches não suportados')
    # Conservative safety policy (not a SQL security boundary).
    if re.search(r'\b(?:BEGIN\s+TRAN(?:SACTION)?|COMMIT|ROLLBACK|SAVE\s+TRAN|USE\s+\w+|EXEC(?:UTE)?|xp_\w+|sp_configure|OPENROWSET|OPENDATASOURCE|BULK\s+INSERT)\b', s, re.I):
        raise ValueError('Comando de controle de transação, execução dinâmica ou operação especial não suportado')
    if action == 'query':
        # Block obvious writes and side-effecting queries, including SELECT INTO.
        if not re.match(r'^\s*(?:SELECT|WITH)\b', s, re.I) or re.search(r'\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|INTO|EXEC|GRANT|REVOKE|DENY|DBCC|BACKUP|RESTORE)\b', s, re.I):
            raise ValueError('query aceita somente SELECT/CTE sem palavras-chave de escrita; use permissão de leitura')
    else:
        if re.search(r'\b(?:BACKUP|RESTORE|SHUTDOWN|RECONFIGURE|CREATE\s+DATABASE|ALTER\s+DATABASE|DROP\s+DATABASE|CREATE\s+LOGIN|ALTER\s+LOGIN|DROP\s+LOGIN)\b', s, re.I):
            raise ValueError('Operação administrativa fora do escopo do executor transacional')
    return s


def sqlcmd_path():
    custom = os.getenv('MSSQL_SQLCMD_PATH', '').strip()
    if custom:
        if not Path(custom).expanduser().is_file():
            raise ValueError('MSSQL_SQLCMD_PATH não corresponde a um executável existente')
        return str(Path(custom).expanduser())
    return shutil.which('sqlcmd')


def wrapped(sql, mode, apply):
    if mode == 'ping':
        return "SET NOCOUNT ON; SELECT DB_NAME() AS database_name, SYSTEM_USER AS login_name, @@SERVERNAME AS server_name, @@VERSION AS version;"
    # XACT_ABORT + TRY/CATCH: avoid reporting successful preview/apply on failure.
    lines = ['SET NOCOUNT ON;', 'SET XACT_ABORT ON;', 'BEGIN TRY', 'BEGIN TRANSACTION;', sql.rstrip(';') + ';']
    lines += ['COMMIT TRANSACTION;' if apply and mode == 'execute' else 'ROLLBACK TRANSACTION;']
    lines += ['END TRY', 'BEGIN CATCH', 'IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;', 'THROW;', 'END CATCH;']
    return '\n'.join(lines)


def output(payload):
    print(json.dumps(payload, ensure_ascii=False, default=str))


def via_sqlcmd(args, cfg, sql):
    exe = sqlcmd_path()
    if not exe:
        raise ValueError('sqlcmd não encontrado: configure MSSQL_SQLCMD_PATH ou MSSQL_CLIENT=python')
    # sqlcmd ODBC standard switches; encryption flags vary between sqlcmd implementations.
    # Reject ambiguous TLS mode; prefer pyodbc for explicitly configured TLS policy.
    if cfg['encrypt'] not in ('yes', 'mandatory') or cfg['trust'] != 'no':
        raise ValueError('Para políticas TLS não padrão use MSSQL_CLIENT=python (pyodbc)')
    cmd = [exe, '-S', f"tcp:{cfg['host']},{cfg['port']}", '-d', cfg['db'], '-U', cfg['user'],
           '-b', '-N', '-l', '5', '-t', str(cfg['timeout']), '-h', '-1', '-W', '-w', '65535', '-i']
    sqltext = wrapped(sql, args.command, args.apply if args.command == 'execute' else False)
    filename = None
    try:
        # sqlcmd -i requires a file. Restrictive permissions, deleted on exit.
        fd, filename = tempfile.mkstemp(prefix='mssql_skill_', suffix='.sql')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(sqltext)
        env = os.environ.copy()
        env['SQLCMDPASSWORD'] = cfg['password']
        completed = subprocess.run(cmd + [filename], env=env, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', timeout=cfg['timeout'] + 15)
        if completed.returncode:
            output({'ok': False, 'backend': 'sqlcmd', 'error': 'Falha na consulta/execução; detalhes potencialmente sensíveis omitidos', 'exit_code': completed.returncode})
            return 1
        raw = completed.stdout
        output({'ok': True, 'backend': 'sqlcmd', 'mode': args.command,
                'text': raw[:65536], 'truncated': len(raw) > 65536,
                'transaction': 'not_applicable' if args.command == 'ping' else ('committed' if args.command == 'execute' and args.apply else 'rolled_back'),
                'persisted': args.command == 'execute' and args.apply})
        return 0
    except subprocess.TimeoutExpired:
        raise ValueError('Timeout do sqlcmd: estado do commit pode ser indeterminado; valide antes de repetir')
    finally:
        if filename:
            try:
                os.unlink(filename)
            except OSError:
                pass


def via_pyodbc(args, cfg, sql):
    try:
        import pyodbc
    except ImportError as e:
        raise ValueError('Instale pyodbc e um Microsoft ODBC Driver SQL Server compatível') from e
    driver = os.getenv('MSSQL_ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')
    # escape ODBC brace values, keep password out of command line.
    def brace(v):
        return '{' + str(v).replace('}', '}}') + '}'
    connstr = ';'.join((f'DRIVER={brace(driver)}', f'SERVER={brace(f"tcp:{cfg["host"]},{cfg["port"]}")}',
                        f'DATABASE={brace(cfg["db"])}', f'UID={brace(cfg["user"])}', f'PWD={brace(cfg["password"])}',
                        f'Encrypt={cfg["encrypt"]}', f'TrustServerCertificate={cfg["trust"]}', 'Connection Timeout=5'))
    try:
        cn = pyodbc.connect(connstr, autocommit=False, timeout=5)
        try:
            cursor = cn.cursor()
            cursor.timeout = cfg['timeout']
            if args.command == 'ping':
                cursor.execute('SELECT DB_NAME(), SYSTEM_USER, @@SERVERNAME, @@VERSION')
                r = cursor.fetchone()
                cn.rollback()
                output({'ok': True, 'backend': 'python', 'database': r[0], 'user': r[1], 'server': r[2], 'version': r[3]})
                return 0
            cursor.execute('SET XACT_ABORT ON')
            cursor.execute(sql)
            rows = []
            truncated = False
            if cursor.description:
                cols = [c[0] for c in cursor.description]
                data = cursor.fetchmany(args.limit + 1)
                rows = [dict(zip(cols, r)) for r in data[:args.limit]]
                truncated = len(data) > args.limit
            affected = cursor.rowcount
            if args.command == 'execute' and args.apply:
                cn.commit()
                state = 'committed'
            else:
                cn.rollback()
                state = 'rolled_back'
            output({'ok': True, 'backend': 'python', 'mode': args.command, 'rows': rows, 'truncated': truncated,
                    'rowcount': affected, 'transaction': state, 'persisted': state == 'committed'})
            return 0
        except Exception:
            try:
                cn.rollback()
            except Exception:
                pass
            raise
        finally:
            cn.close()
    except pyodbc.Error:
        output({'ok': False, 'backend': 'python', 'error': 'Falha ODBC/SQL Server; detalhes omitidos para proteger credenciais e dados'})
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file', help='Arquivo explícito; padrão projeto/.env, fallback skill/.env')
    p.add_argument('--client', choices=['auto', 'sqlcmd', 'python'])
    subs = p.add_subparsers(dest='command', required=True)
    subs.add_parser('ping')
    for name in ['query', 'execute']:
        sp = subs.add_parser(name)
        src = sp.add_mutually_exclusive_group(required=True)
        src.add_argument('--sql')
        src.add_argument('--file', type=Path)
        sp.add_argument('--limit', type=int, default=100)
        if name == 'execute':
            sp.add_argument('--apply', action='store_true')
            sp.add_argument('--ack', choices=['confirmed'])
    a = p.parse_args()
    try:
        load_env(a.env_file)
        cfg = conf()
        if a.command != 'ping':
            if not 1 <= a.limit <= 1000:
                raise ValueError('--limit fora do intervalo 1..1000')
            raw = a.sql if a.sql is not None else a.file.read_text(encoding='utf-8-sig')
            sql = statement(raw, a.command)
        else:
            sql = ''
        if a.command == 'execute' and a.apply and a.ack != 'confirmed':
            raise ValueError('A execução persistente exige aprovação humana e --apply --ack confirmed')
        client = (a.client or os.getenv('MSSQL_CLIENT', 'auto')).lower()
        if client not in ('auto', 'sqlcmd', 'python'):
            raise ValueError('MSSQL_CLIENT deve ser auto, sqlcmd ou python')
        if client == 'auto':
            client = 'sqlcmd' if sqlcmd_path() and cfg['encrypt'] in ('yes', 'mandatory') and cfg['trust'] == 'no' else 'python'
        return via_sqlcmd(a, cfg, sql) if client == 'sqlcmd' else via_pyodbc(a, cfg, sql)
    except (ValueError, OSError, UnicodeError) as e:
        output({'ok': False, 'error': str(e)})
        return 2

if __name__ == '__main__':
    sys.exit(main())
