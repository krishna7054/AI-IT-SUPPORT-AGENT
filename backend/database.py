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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS license_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                license_name TEXT NOT NULL,
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, license_name),
                FOREIGN KEY (user_id) REFERENCES users(id)
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
        connection.execute("DROP TABLE IF EXISTS license_assignments")
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
        license_totals = connection.execute(
            """
            SELECT COUNT(*) AS assigned_licenses
            FROM license_assignments
            """
        ).fetchone()
    return {
        "total_users": int(totals["total_users"] or 0),
        "active_users": int(totals["active_users"] or 0),
        "locked_users": int(totals["locked_users"] or 0),
        "assigned_licenses": int(license_totals["assigned_licenses"] or 0),
    }


def available_licenses() -> list[str]:
    return ["Google Workspace", "Slack", "Zoom", "VPN", "Okta"]


def user_has_license(email: str, license_name: str) -> bool:
    normalized_email = email.strip().lower()
    normalized_license = license_name.strip().lower()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM license_assignments la
            JOIN users u ON u.id = la.user_id
            WHERE lower(u.email) = ? AND lower(la.license_name) = ?
            """,
            (normalized_email, normalized_license),
        ).fetchone()
    return row is not None


def assign_license(email: str, license_name: str) -> dict[str, Any]:
    user = get_user_by_email(email)
    normalized_license = license_name.strip()

    if user is None:
        raise LookupError("User not found.")
    if not normalized_license:
        raise ValueError("License is required.")
    if normalized_license not in available_licenses():
        raise ValueError("Unsupported license.")
    if user_has_license(user["email"], normalized_license):
        raise ValueError("License is already assigned to this user.")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO license_assignments (user_id, license_name)
            VALUES (?, ?)
            """,
            (user["id"], normalized_license),
        )
        connection.commit()

    return {
        "email": user["email"],
        "full_name": user["full_name"],
        "license_name": normalized_license,
    }


def list_license_assignments() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                la.id,
                u.full_name,
                u.email,
                la.license_name,
                la.assigned_at
            FROM license_assignments la
            JOIN users u ON u.id = la.user_id
            ORDER BY la.assigned_at DESC, u.full_name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]
