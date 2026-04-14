from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


DB_PATH = Path("data") / "it_admin.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                department TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                password TEXT NOT NULL,
                locked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    seed_users()


def seed_users() -> None:
    users = [
        {
            "full_name": "John Carter",
            "email": "john@company.com",
            "department": "IT",
            "status": "active",
            "password": "Welcome@123",
            "locked": 0,
        },
        {
            "full_name": "Alice Wong",
            "email": "alice@company.com",
            "department": "HR",
            "status": "active",
            "password": "Welcome@123",
            "locked": 0,
        },
        {
            "full_name": "Priya Nair",
            "email": "priya@company.com",
            "department": "Finance",
            "status": "suspended",
            "password": "ResetMe@123",
            "locked": 1,
        },
    ]

    with get_connection() as connection:
        existing = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        if existing and existing["count"] > 0:
            return

        connection.executemany(
            """
            INSERT INTO users (full_name, email, department, status, password, locked)
            VALUES (:full_name, :email, :department, :status, :password, :locked)
            """,
            users,
        )
        connection.commit()


def reset_demo_data() -> None:
    with get_connection() as connection:
        connection.execute("DROP TABLE IF EXISTS users")
        connection.commit()
    init_db()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_users() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, full_name, email, department, status, password, locked, created_at, updated_at
            FROM users
            ORDER BY full_name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_by_email(email: str) -> dict[str, Any] | None:
    normalized_email = email.strip().lower()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, full_name, email, department, status, password, locked, created_at, updated_at
            FROM users
            WHERE lower(email) = ?
            """,
            (normalized_email,),
        ).fetchone()
    return row_to_dict(row)


def create_user(full_name: str, email: str, department: str, password: str = "Welcome@123") -> dict[str, Any]:
    normalized_name = full_name.strip()
    normalized_email = email.strip().lower()
    normalized_department = department.strip()

    if not normalized_name:
        raise ValueError("Full name is required.")
    if not normalized_email:
        raise ValueError("Email is required.")
    if not normalized_department:
        raise ValueError("Department is required.")
    if get_user_by_email(normalized_email):
        raise ValueError("A user with that email already exists.")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (full_name, email, department, status, password, locked, updated_at)
            VALUES (?, ?, ?, 'active', ?, 0, CURRENT_TIMESTAMP)
            """,
            (normalized_name, normalized_email, normalized_department, password),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, full_name, email, department, status, password, locked, created_at, updated_at
            FROM users
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row) or {}


def reset_password(email: str, new_password: str = "TempPass!2026") -> dict[str, Any]:
    user = get_user_by_email(email)
    if user is None:
        raise LookupError("User not found.")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET password = ?, updated_at = CURRENT_TIMESTAMP
            WHERE lower(email) = ?
            """,
            (new_password, email.strip().lower()),
        )
        connection.commit()
    return get_user_by_email(email) or {}


def unlock_user(email: str) -> dict[str, Any]:
    user = get_user_by_email(email)
    if user is None:
        raise LookupError("User not found.")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET locked = 0, status = 'active', updated_at = CURRENT_TIMESTAMP
            WHERE lower(email) = ?
            """,
            (email.strip().lower(),),
        )
        connection.commit()
    return get_user_by_email(email) or {}


def dashboard_stats() -> dict[str, int]:
    with get_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_users,
                SUM(CASE WHEN locked = 1 THEN 1 ELSE 0 END) AS locked_users
            FROM users
            """
        ).fetchone()
    return {
        "total_users": int(totals["total_users"] or 0),
        "active_users": int(totals["active_users"] or 0),
        "locked_users": int(totals["locked_users"] or 0),
    }
