"""Database layer for the SQLite Lab MCP server.

All identifier validation happens here so the MCP layer never builds SQL
from raw user input:

- table/column names are checked against the live schema (sqlite_master /
  PRAGMA table_info) before being interpolated as quoted identifiers
- filter operators and aggregate metrics come from fixed whitelists
- every VALUE is bound as a ? parameter, never formatted into the SQL string
"""

import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "lab.db"

ALLOWED_OPERATORS = {"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN"}
ALLOWED_METRICS = {"count", "avg", "sum", "min", "max"}
MAX_LIMIT = 100


class ValidationError(Exception):
    """Raised when a request cannot be safely executed."""


class SQLiteAdapter:
    """SQLite implementation of the database layer.

    Keeps a swappable surface (list_tables / get_table_schema / search /
    insert / aggregate) so a PostgreSQL adapter could replace it later.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise ValidationError(
                f"Database file not found at {self.db_path}. Run init_db.py first."
            )
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Schema inspection
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        rows = self._query(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in rows]

    def get_table_schema(self, table: str) -> dict[str, Any]:
        table = self._validate_table(table)
        rows = self._query(f'PRAGMA table_info("{table}")')
        columns = [
            {
                "name": row["name"],
                "type": row["type"],
                "not_null": bool(row["notnull"]),
                "default": row["dflt_value"],
                "primary_key": bool(row["pk"]),
            }
            for row in rows
        ]
        return {"table": table, "columns": columns}

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        table = self._validate_table(table)
        if columns:
            self._validate_columns(table, columns)
            select_clause = ", ".join(f'"{c}"' for c in columns)
        else:
            select_clause = "*"

        if not isinstance(limit, int) or limit < 1:
            raise ValidationError("limit must be an integer >= 1.")
        if not isinstance(offset, int) or offset < 0:
            raise ValidationError("offset must be an integer >= 0.")
        limit = min(limit, MAX_LIMIT)

        where, params = self._build_where(table, filters)
        order = ""
        if order_by:
            self._validate_columns(table, [order_by], what="order_by column")
            order = f' ORDER BY "{order_by}" {"DESC" if descending else "ASC"}'

        conn = self.connect()
        try:
            total = conn.execute(
                f'SELECT COUNT(*) AS n FROM "{table}"{where}', params
            ).fetchone()["n"]
            rows = [
                dict(r)
                for r in conn.execute(
                    f'SELECT {select_clause} FROM "{table}"{where}{order} LIMIT ? OFFSET ?',
                    [*params, limit, offset],
                ).fetchall()
            ]
        finally:
            conn.close()
        return {"rows": rows, "total": total, "limit": limit, "offset": offset}

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        table = self._validate_table(table)
        if not isinstance(values, dict) or not values:
            raise ValidationError("values must be a non-empty dict of {column: value}.")
        self._validate_columns(table, list(values.keys()))
        for col, value in values.items():
            if value is not None and not isinstance(value, (str, int, float)):
                raise ValidationError(
                    f"Value for '{col}' must be a string, a number, or null."
                )

        cols = ", ".join(f'"{c}"' for c in values)
        placeholders = ", ".join("?" for _ in values)
        conn = self.connect()
        try:
            cur = conn.execute(
                f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})',
                list(values.values()),
            )
            conn.commit()
            new_id = cur.lastrowid
            row = conn.execute(
                f'SELECT * FROM "{table}" WHERE rowid = ?', (new_id,)
            ).fetchone()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise ValidationError(f"Insert violates a database constraint: {exc}") from exc
        finally:
            conn.close()
        return {"id": new_id, "inserted": dict(row) if row else values}

    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        table = self._validate_table(table)
        if not isinstance(metric, str) or metric.lower() not in ALLOWED_METRICS:
            raise ValidationError(
                f"Unsupported metric '{metric}'. Allowed: {sorted(ALLOWED_METRICS)}."
            )
        metric = metric.lower()

        if metric == "count" and column is None:
            target = "*"
        else:
            if column is None:
                raise ValidationError(f"Metric '{metric}' requires a 'column'.")
            self._validate_columns(table, [column])
            target = f'"{column}"'

        where, params = self._build_where(table, filters)
        if group_by:
            self._validate_columns(table, [group_by], what="group_by column")
            sql = (
                f'SELECT "{group_by}" AS "group", {metric.upper()}({target}) AS value '
                f'FROM "{table}"{where} GROUP BY "{group_by}" ORDER BY "{group_by}"'
            )
        else:
            sql = f'SELECT {metric.upper()}({target}) AS value FROM "{table}"{where}'
        rows = self._query(sql, params)
        return {"metric": metric, "column": column, "group_by": group_by, "rows": rows}

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_table(self, table: Any) -> str:
        if not isinstance(table, str) or not table.strip():
            raise ValidationError("Table name must be a non-empty string.")
        tables = self.list_tables()
        if table not in tables:
            raise ValidationError(
                f"Unknown table '{table}'. Available tables: {', '.join(tables)}."
            )
        return table

    def _table_columns(self, table: str) -> list[str]:
        rows = self._query(f'PRAGMA table_info("{table}")')
        return [row["name"] for row in rows]

    def _validate_columns(
        self, table: str, columns: list[Any], what: str = "column"
    ) -> None:
        valid = self._table_columns(table)
        for col in columns:
            if not isinstance(col, str) or col not in valid:
                raise ValidationError(
                    f"Unknown {what} '{col}' in table '{table}'. "
                    f"Valid columns: {', '.join(valid)}."
                )

    def _build_where(
        self, table: str, filters: dict[str, Any] | None
    ) -> tuple[str, list[Any]]:
        if not filters:
            return "", []
        if not isinstance(filters, dict):
            raise ValidationError(
                "filters must be a dict of {column: value} for equality, or "
                "{column: {'op': <operator>, 'value': <value>}}."
            )
        self._validate_columns(table, list(filters.keys()), what="filter column")

        clauses: list[str] = []
        params: list[Any] = []
        for col, spec in filters.items():
            if isinstance(spec, dict):
                if set(spec.keys()) != {"op", "value"}:
                    raise ValidationError(
                        f"Filter for '{col}' must have exactly the keys 'op' and 'value'."
                    )
                op = str(spec["op"]).upper().strip()
                value = spec["value"]
            else:
                op, value = "=", spec

            if op not in ALLOWED_OPERATORS:
                raise ValidationError(
                    f"Unsupported operator '{op}'. Allowed: {sorted(ALLOWED_OPERATORS)}."
                )
            if op == "IN":
                if not isinstance(value, (list, tuple)) or not value:
                    raise ValidationError(
                        f"IN filter for '{col}' requires a non-empty list of values."
                    )
                self._check_scalar_values(col, value)
                clauses.append(f'"{col}" IN ({", ".join("?" for _ in value)})')
                params.extend(value)
            else:
                self._check_scalar_values(col, [value])
                clauses.append(f'"{col}" {op} ?')
                params.append(value)
        return " WHERE " + " AND ".join(clauses), params

    @staticmethod
    def _check_scalar_values(col: str, values: Any) -> None:
        for value in values:
            if not isinstance(value, (str, int, float)):
                raise ValidationError(
                    f"Filter value for '{col}' must be a string or a number, "
                    f"got {type(value).__name__}."
                )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _query(self, sql: str, params: list[Any] | tuple = ()) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()
