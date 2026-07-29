from __future__ import annotations

import os
import sqlite3
import tempfile

from app.tools.database_tool import DatabaseTool


class TestDatabaseTool:
    def test_name_and_version(self) -> None:
        tool = DatabaseTool()
        assert tool.name == "database_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = DatabaseTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "database" in names
        assert "sql" in names

    def test_required_params(self) -> None:
        tool = DatabaseTool()
        assert tool.metadata.parameters[0].required is True
        assert tool.metadata.parameters[1].required is True

    def test_permissions(self) -> None:
        tool = DatabaseTool()
        assert "tools.database.query" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = DatabaseTool()
        assert "sql_query" in tool.metadata.capabilities

    def test_validate_missing_action(self) -> None:
        tool = DatabaseTool()
        errors = tool.validate_params({"database": ":memory:"})
        assert any("action" in e for e in errors)

    def test_validate_missing_database(self) -> None:
        tool = DatabaseTool()
        errors = tool.validate_params({"action": "query"})
        assert any("database" in e for e in errors)

    def test_tables_action(self) -> None:
        tool = DatabaseTool()
        result = tool.execute({"action": "tables", "database": ":memory:"})
        assert result.success
        assert result.output["table_count"] == 0
        assert result.output["tables"] == []

    def test_execute_create_table(self) -> None:
        tool = DatabaseTool()
        result = tool.execute({"action": "execute", "database": ":memory:", "sql": "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)"})
        assert result.success
        assert result.output.get("affected_rows") == 0

    def test_execute_insert(self) -> None:
        tool = DatabaseTool()
        tool.execute({"action": "execute", "database": ":memory:", "sql": "CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"})
        result = tool.execute({"action": "execute", "database": ":memory:", "sql": "INSERT INTO t (name) VALUES ('hello')"})
        assert result.success
        assert result.output.get("affected_rows") == 1

    def test_query_returns_rows(self) -> None:
        tool = DatabaseTool()
        tool.execute({"action": "execute", "database": ":memory:", "sql": "CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"})
        tool.execute({"action": "execute", "database": ":memory:", "sql": "INSERT INTO t (name) VALUES ('alice')"})
        tool.execute({"action": "execute", "database": ":memory:", "sql": "INSERT INTO t (name) VALUES ('bob')"})
        result = tool.execute({"action": "query", "database": ":memory:", "sql": "SELECT * FROM t ORDER BY id"})
        assert result.success
        assert len(result.output["rows"]) == 2
        assert result.output["columns"] == ["id", "name"]

    def test_query_with_params(self) -> None:
        tool = DatabaseTool()
        tool.execute({"action": "execute", "database": ":memory:", "sql": "CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"})
        tool.execute({"action": "execute", "database": ":memory:", "sql": "INSERT INTO t (name) VALUES ('x')"})
        result = tool.execute({"action": "query", "database": ":memory:", "sql": "SELECT * FROM t WHERE name = ?", "params": ["x"]})
        assert result.success
        assert len(result.output["rows"]) == 1

    def test_schema_action(self) -> None:
        tool = DatabaseTool()
        tool.execute({"action": "execute", "database": ":memory:", "sql": "CREATE TABLE test_schema (id INTEGER)"})
        result = tool.execute({"action": "schema", "database": ":memory:"})
        assert result.success
        assert "test_schema" in result.output["schemas"]

    def test_schema_for_specific_table(self) -> None:
        tool = DatabaseTool()
        tool.execute({"action": "execute", "database": ":memory:", "sql": "CREATE TABLE specific_t (id INTEGER, val TEXT)"})
        result = tool.execute({"action": "schema", "database": ":memory:", "sql": "specific_t"})
        assert result.success
        assert "specific_t" in result.output["schema"]

    def test_schema_table_not_found(self) -> None:
        tool = DatabaseTool()
        result = tool.execute({"action": "schema", "database": ":memory:", "sql": "nonexistent"})
        assert not result.success

    def test_execute_without_sql(self) -> None:
        tool = DatabaseTool()
        result = tool.execute({"action": "execute", "database": ":memory:"})
        assert not result.success
        assert "sql" in (result.error_message or "")

    def test_query_without_sql(self) -> None:
        tool = DatabaseTool()
        result = tool.execute({"action": "query", "database": ":memory:"})
        assert not result.success
        assert "sql" in (result.error_message or "")

    def test_unknown_action(self) -> None:
        tool = DatabaseTool()
        result = tool.execute({"action": "unknown", "database": ":memory:"})
        assert not result.success

    def test_file_based_db(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            tool = DatabaseTool()
            result = tool.execute({"action": "execute", "database": db_path, "sql": "CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"})
            assert result.success
            result = tool.execute({"action": "tables", "database": db_path})
            assert "t" in result.output["tables"]
        finally:
            tool.close(db_path)
            os.unlink(db_path)

    def test_to_dict(self) -> None:
        tool = DatabaseTool()
        d = tool.to_dict()
        assert d["name"] == "database_tool"
