"""Testes unitários isolados para scripts/mssql_tool.py usando unittest e unittest.mock."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakePyodbcError(Exception):
    """Exceção simulada de pyodbc.Error para ambientes sem pyodbc instalado."""


def _ensure_fake_pyodbc() -> types.ModuleType:
    """Garante um módulo pyodbc simulável em sys.modules caso não esteja instalado."""
    if "pyodbc" in sys.modules and sys.modules["pyodbc"] is not None:
        return sys.modules["pyodbc"]
    fake_mod = types.ModuleType("pyodbc")
    fake_mod.Error = FakePyodbcError  # type: ignore[attr-defined]
    fake_mod.connect = MagicMock()  # type: ignore[attr-defined]
    fake_mod.drivers = MagicMock(return_value=["ODBC Driver 18 for SQL Server"])  # type: ignore[attr-defined]
    sys.modules["pyodbc"] = fake_mod
    return fake_mod


_ensure_fake_pyodbc()

from scripts import mssql_tool  # noqa: E402


class TestMssqlTool(unittest.TestCase):
    """Suíte de testes unitários para validação de configuração, conexão, execução e formatação."""

    def setUp(self) -> None:
        self._env_backup = os.environ.copy()
        for key in (
            "MSSQL_HOST",
            "MSSQL_PORT",
            "MSSQL_DATABASE",
            "MSSQL_USER",
            "MSSQL_PASSWORD",
            "MSSQL_ODBC_DRIVER",
            "MSSQL_ENCRYPT",
            "MSSQL_TRUST_SERVER_CERTIFICATE",
            "MSSQL_COMMAND_TIMEOUT",
        ):
            os.environ.pop(key, None)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text(
            "\n".join(
                [
                    "MSSQL_HOST=127.0.0.1",
                    "MSSQL_PORT=1433",
                    "MSSQL_DATABASE=vendas_db",
                    "MSSQL_USER=sa",
                    "MSSQL_PASSWORD=Segredo}123",
                    "MSSQL_ODBC_DRIVER=ODBC Driver 18 for SQL Server",
                    "MSSQL_ENCRYPT=yes",
                    "MSSQL_TRUST_SERVER_CERTIFICATE=yes",
                    "MSSQL_COMMAND_TIMEOUT=45",
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self.temp_dir.cleanup()

    def test_load_db_config_success_and_timeout_override(self) -> None:
        cfg = mssql_tool.load_db_config(self.env_path)
        self.assertEqual(cfg["host"], "127.0.0.1")
        self.assertEqual(cfg["port"], 1433)
        self.assertEqual(cfg["db"], "vendas_db")
        self.assertEqual(cfg["user"], "sa")
        self.assertEqual(cfg["password"], "Segredo}123")
        self.assertEqual(cfg["trust"], "yes")
        self.assertEqual(cfg["timeout"], 45)

        cfg_override = mssql_tool.load_db_config(self.env_path, timeout_override=90)
        self.assertEqual(cfg_override["timeout"], 90)

    def test_load_db_config_missing_file_raises_config_error(self) -> None:
        missing_path = Path(self.temp_dir.name) / "nao_existe.env"
        with self.assertRaises(mssql_tool.ConfigError) as ctx:
            mssql_tool.load_db_config(missing_path)
        self.assertIn("Arquivo .env não encontrado", str(ctx.exception))

    def test_load_db_config_missing_required_vars(self) -> None:
        incomplete_env = Path(self.temp_dir.name) / "incomplete.env"
        incomplete_env.write_text("MSSQL_HOST=localhost\n", encoding="utf-8")
        with self.assertRaises(mssql_tool.ConfigError) as ctx:
            mssql_tool.load_db_config(incomplete_env)
        self.assertIn("MSSQL_DATABASE", str(ctx.exception))
        self.assertIn("MSSQL_USER", str(ctx.exception))
        self.assertIn("MSSQL_PASSWORD", str(ctx.exception))

    def test_load_db_config_invalid_numeric_values(self) -> None:
        invalid_env = Path(self.temp_dir.name) / "invalid.env"
        invalid_env.write_text(
            "MSSQL_HOST=127.0.0.1\nMSSQL_DATABASE=db\nMSSQL_USER=u\nMSSQL_PASSWORD=p\nMSSQL_PORT=abc\n",
            encoding="utf-8",
        )
        with self.assertRaises(mssql_tool.ConfigError):
            mssql_tool.load_db_config(invalid_env)

    def test_build_connection_string_escapes_braces(self) -> None:
        cfg = mssql_tool.load_db_config(self.env_path)
        conn_str = mssql_tool.build_connection_string(cfg)
        self.assertIn("DRIVER={ODBC Driver 18 for SQL Server}", conn_str)
        self.assertIn("SERVER={tcp:127.0.0.1,1433}", conn_str)
        self.assertIn("DATABASE={vendas_db}", conn_str)
        self.assertIn("UID={sa}", conn_str)
        self.assertIn("PWD={Segredo}}123}", conn_str)
        self.assertIn("Encrypt=yes", conn_str)
        self.assertIn("TrustServerCertificate=yes", conn_str)
        self.assertIn("Connection Timeout=45", conn_str)

    @patch("pyodbc.connect")
    def test_ping_server_success(self, mock_connect: MagicMock) -> None:
        mock_cn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [
            ("database",),
            ("user",),
            ("server",),
            ("version",),
        ]
        mock_cursor.fetchone.return_value = (
            "vendas_db",
            "sa",
            "SQL-CONTAINER",
            "Microsoft SQL Server 2022",
        )
        mock_cn.cursor.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_cn

        cfg = mssql_tool.load_db_config(self.env_path)
        result = mssql_tool.ping_server(cfg)

        self.assertTrue(result["ok"])
        self.assertEqual(result["ping"]["database"], "vendas_db")
        self.assertEqual(result["ping"]["server"], "SQL-CONTAINER")
        self.assertEqual(result["exit_code"], mssql_tool.EXIT_SUCCESS)
        mock_connect.assert_called_once()

    @patch("pyodbc.connect")
    def test_execute_sql_select_and_truncation(self, mock_connect: MagicMock) -> None:
        mock_cn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("nome",)]
        mock_cursor.fetchmany.return_value = [(1, "Alice"), (2, "Bob"), (3, "Carol")]
        mock_cn.cursor.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_cn

        cfg = mssql_tool.load_db_config(self.env_path)
        result = mssql_tool.execute_sql(cfg, "SELECT id, nome FROM dbo.Clientes", limit=2)

        self.assertTrue(result["ok"])
        self.assertEqual(result["rowcount"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["columns"], ["id", "nome"])
        self.assertEqual(result["rows"], [{"id": 1, "nome": "Alice"}, {"id": 2, "nome": "Bob"}])

    @patch("pyodbc.connect")
    def test_execute_sql_read_only_blocks_destructive_commands(
        self, mock_connect: MagicMock
    ) -> None:
        cfg = mssql_tool.load_db_config(self.env_path)
        blocked_queries = [
            "INSERT INTO Clientes (nome) VALUES ('Teste')",
            "UPDATE Clientes SET ativo = 0 WHERE id = 1",
            "DELETE FROM Clientes WHERE id = 1",
            "DROP TABLE Clientes",
            "ALTER TABLE Clientes ADD idade INT",
            "TRUNCATE TABLE Clientes",
        ]
        for query in blocked_queries:
            with self.subTest(query=query):
                res = mssql_tool.execute_sql(cfg, query, read_only=True)
                self.assertFalse(res["ok"])
                self.assertEqual(res["error_type"], "security_error")
                self.assertEqual(res["exit_code"], mssql_tool.EXIT_READ_ONLY_ERROR)
                mock_connect.assert_not_called()

    @patch("pyodbc.connect")
    def test_execute_sql_read_only_allows_keywords_in_comments_and_strings(
        self, mock_connect: MagicMock
    ) -> None:
        mock_cn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("acao",)]
        mock_cursor.fetchmany.return_value = [("UPDATE_LOG",)]
        mock_cn.cursor.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_cn

        cfg = mssql_tool.load_db_config(self.env_path)
        sql = """
        -- Comentário falando sobre DROP e DELETE
        /* Outro comentário com TRUNCATE e ALTER */
        SELECT 'UPDATE_LOG' AS acao, [DELETE_FLAG] FROM dbo.Auditoria
        """
        res = mssql_tool.execute_sql(cfg, sql, read_only=True)
        self.assertTrue(res["ok"])
        mock_connect.assert_called_once()

    @patch("pyodbc.drivers", return_value=["ODBC Driver 18 for SQL Server"])
    @patch("pyodbc.connect")
    def test_execute_sql_syntax_error_and_password_sanitization(
        self, mock_connect: MagicMock, _mock_drivers: MagicMock
    ) -> None:
        pyodbc_mod = sys.modules["pyodbc"]
        err_cls = getattr(pyodbc_mod, "Error", Exception)
        mock_connect.side_effect = err_cls(
            "[42000] Incorrect syntax near 'FROM'. PWD=Segredo}123; (102)"
        )

        cfg = mssql_tool.load_db_config(self.env_path)
        res = mssql_tool.execute_sql(cfg, "SELECT * FROM")

        self.assertFalse(res["ok"])
        self.assertEqual(res["error_type"], "sql_error")
        self.assertEqual(res["exit_code"], mssql_tool.EXIT_SQL_ERROR)
        self.assertNotIn("Segredo}123", res["error"])
        self.assertIn("******", res["error"])

    def test_format_output_json_table_and_csv(self) -> None:
        sample = {
            "ok": True,
            "columns": ["id", "nome"],
            "rows": [{"id": 1, "nome": "Ana"}, {"id": 2, "nome": "Bruno"}],
            "rowcount": 2,
            "truncated": False,
            "exit_code": 0,
        }

        json_out = mssql_tool.format_output(sample, "json")
        parsed = json.loads(json_out)
        self.assertTrue(parsed["ok"])
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertNotIn("exit_code", parsed)

        table_out = mssql_tool.format_output(sample, "table")
        self.assertIn("id | nome", table_out)
        self.assertIn("Ana", table_out)
        self.assertIn("(2 linha(s) retornada(s))", table_out)

        csv_out = mssql_tool.format_output(sample, "csv")
        self.assertEqual(csv_out.splitlines(), ["id,nome", "1,Ana", "2,Bruno"])

        with self.assertRaises(ValueError):
            mssql_tool.format_output(sample, "xml")

    @patch("pyodbc.connect")
    def test_cli_main_with_sql_file_and_flags(self, mock_connect: MagicMock) -> None:
        mock_cn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("total",)]
        mock_cursor.fetchmany.return_value = [(42,)]
        mock_cn.cursor.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_cn

        sql_file = Path(self.temp_dir.name) / "query.sql"
        sql_file.write_text("SELECT 42 AS total;", encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = mssql_tool.main(
                [
                    "--env-file",
                    str(self.env_path),
                    "--file",
                    str(sql_file),
                    "--format",
                    "json",
                    "--read-only",
                    "--timeout",
                    "15",
                ]
            )

        self.assertEqual(exit_code, mssql_tool.EXIT_SUCCESS)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["rows"][0]["total"], 42)

    @patch("pyodbc.drivers", return_value=[])
    @patch("pyodbc.connect")
    def test_missing_odbc_driver_returns_driver_error(
        self, mock_connect: MagicMock, _mock_drivers: MagicMock
    ) -> None:
        pyodbc_mod = sys.modules["pyodbc"]
        err_cls = getattr(pyodbc_mod, "Error", Exception)
        mock_connect.side_effect = err_cls("[IM002] Data source name not found")

        cfg = mssql_tool.load_db_config(self.env_path)
        res = mssql_tool.ping_server(cfg)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error_type"], "driver_error")
        self.assertEqual(res["exit_code"], mssql_tool.EXIT_CONNECTION_ERROR)

    @patch("pyodbc.drivers", return_value=["ODBC Driver 18 for SQL Server"])
    @patch("pyodbc.connect")
    def test_ssl_certificate_error_returns_connection_error_with_hint(
        self, mock_connect: MagicMock, _mock_drivers: MagicMock
    ) -> None:
        pyodbc_mod = sys.modules["pyodbc"]
        err_cls = getattr(pyodbc_mod, "Error", Exception)
        mock_connect.side_effect = err_cls(
            "[08001] SSL Provider: [error:0A000086:certificate verify failed:self signed certificate]"
        )

        cfg = mssql_tool.load_db_config(self.env_path)
        res = mssql_tool.ping_server(cfg)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error_type"], "connection_error")
        self.assertEqual(res["exit_code"], mssql_tool.EXIT_CONNECTION_ERROR)
        self.assertIn("MSSQL_TRUST_SERVER_CERTIFICATE=yes", res.get("hint", ""))

    @patch("pyodbc.connect")
    def test_execute_sql_dml_rowcount_and_cli_exit_codes(
        self, mock_connect: MagicMock
    ) -> None:
        mock_cn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.rowcount = 5
        mock_cn.cursor.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_cn

        cfg = mssql_tool.load_db_config(self.env_path)
        dml_res = mssql_tool.execute_sql(
            cfg, "UPDATE dbo.Clientes SET ativo = 1", read_only=False
        )
        self.assertTrue(dml_res["ok"])
        self.assertEqual(dml_res["rowcount"], 5)
        self.assertIn("Linhas afetadas: 5", mssql_tool.format_output(dml_res, "table"))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code_ro = mssql_tool.main(
                [
                    "--env-file",
                    str(self.env_path),
                    "--sql",
                    "DROP TABLE dbo.Clientes",
                    "--read-only",
                ]
            )
        self.assertEqual(code_ro, mssql_tool.EXIT_READ_ONLY_ERROR)

        with contextlib.redirect_stdout(stdout):
            code_cfg = mssql_tool.main(
                [
                    "--env-file",
                    str(Path(self.temp_dir.name) / "inexistente.env"),
                    "--ping",
                ]
            )
        self.assertEqual(code_cfg, mssql_tool.EXIT_CONFIG_ERROR)


if __name__ == "__main__":
    unittest.main()
