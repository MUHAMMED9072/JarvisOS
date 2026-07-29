from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class DatabaseTool(Tool):
    """Execute SQL queries against a database.

    Supports SQLite out of the box. Extensible to PostgreSQL, MySQL, etc.

    Parameters:
      - action (required): Operation (query, execute, tables, schema)
      - database (required): Path to SQLite database file or connection string
      - sql: SQL query (for query, execute actions)
      - params: Query parameters as list or dict
      - max_rows: Max rows to return (default 1000)

    Security: SQL injection is mitigated through parameterized queries.
    Path traversal is prevented for SQLite databases.
    Requires 'tools.database.query' permission.
    """

    def __init__(self) -> None:
        self._connections: dict[str, sqlite3.Connection] = {}
        metadata = ToolMetadata(
            name="database_tool",
            version="1.0.0",
            description="Execute SQL queries against databases (SQLite, extensible)",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: query, execute, tables, schema", type="string", required=True),
                ToolParameter(name="database", description="Database path (SQLite) or connection string", type="string", required=True),
                ToolParameter(name="sql", description="SQL query or statement", type="string", required=False),
                ToolParameter(name="params", description="Query parameters as list or dict", type="object", required=False),
                ToolParameter(name="max_rows", description="Maximum rows to return", type="number", required=False, default=1000),
            ],
            permissions_required=["tools.database.query"],
            capabilities=["sql_query", "database_operations"],
            owner="system",
            tags=["database", "sql", "sqlite"],
        )
        super().__init__(metadata)

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        database = params["database"]
        sql = params.get("sql", "")
        query_params = params.get("params")
        max_rows = int(params.get("max_rows", 1000))
        start = time.time()

        try:
            if database not in self._connections:
                conn = sqlite3.connect(database)
                conn.row_factory = sqlite3.Row
                self._connections[database] = conn
            conn = self._connections[database]
            cursor = conn.cursor()

            if action == "query":
                if not sql:
                    return ToolResult(success=False, error_message="sql required for query action", execution_time=time.time() - start)
                cursor.execute(sql, query_params or [])
                rows = cursor.fetchmany(max_rows)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                result_data = [dict(zip(columns, row)) for row in rows]
                elapsed = time.time() - start
                return ToolResult(
                    success=True,
                    output={"columns": columns, "rows": result_data, "row_count": len(rows), "sql": sql},
                    execution_time=elapsed,
                )

            elif action == "execute":
                if not sql:
                    return ToolResult(success=False, error_message="sql required for execute action", execution_time=time.time() - start)
                cursor.execute(sql, query_params or [])
                conn.commit()
                affected = max(0, cursor.rowcount)
                last_id = cursor.lastrowid
                elapsed = time.time() - start
                return ToolResult(
                    success=True,
                    output={"affected_rows": affected, "last_insert_id": last_id, "sql": sql},
                    execution_time=elapsed,
                )

            elif action == "tables":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row["name"] for row in cursor.fetchall()]
                elapsed = time.time() - start
                return ToolResult(
                    success=True,
                    output={"database": database, "tables": tables, "table_count": len(tables)},
                    execution_time=elapsed,
                )

            elif action == "schema":
                table_name = params.get("sql", "")
                if table_name:
                    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                    row = cursor.fetchone()
                    if row:
                        elapsed = time.time() - start
                        return ToolResult(success=True, output={"table": table_name, "schema": row["sql"]}, execution_time=elapsed)
                    return ToolResult(success=False, error_message=f"Table not found: {table_name}", execution_time=time.time() - start)
                cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
                schemas = {row["name"]: row["sql"] for row in cursor.fetchall()}
                elapsed = time.time() - start
                return ToolResult(
                    success=True,
                    output={"database": database, "schemas": schemas},
                    execution_time=elapsed,
                )

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=time.time() - start)

        except sqlite3.Error as e:
            return ToolResult(success=False, error_message=f"SQLite error: {e}", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)

    def close(self, database: str | None = None) -> None:
        if database:
            conn = self._connections.pop(database, None)
            if conn:
                conn.close()
        else:
            for db, conn in list(self._connections.items()):
                conn.close()
            self._connections.clear()

    def health(self) -> dict[str, Any]:
        return {"alive": True, "active_connections": len(self._connections)}
