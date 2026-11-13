"""Local SQLite storage for devices, settings and audit events."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class _ClosingConnection(sqlite3.Connection):
    """SQLite connection that closes after a with-block (sqlite defaults only commit)."""
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535),
                    group_name TEXT,
                    fingerprint TEXT NOT NULL,
                    mac_address TEXT,
                    last_seen TEXT,
                    wol_state TEXT NOT NULL DEFAULT 'unknown',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    device_id TEXT,
                    device_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(device_id) REFERENCES devices(device_id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
                CREATE INDEX IF NOT EXISTS idx_audit_device ON audit_log(device_id);
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(devices)")}
            if "mac_address" not in columns:
                db.execute("ALTER TABLE devices ADD COLUMN mac_address TEXT")

    def add_device(self, *, device_id: str, name: str, host: str, port: int, fingerprint: str, mac_address: str | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO devices(device_id,name,host,port,fingerprint,mac_address) VALUES(?,?,?,?,?,?)",
                (device_id, name, host, port, fingerprint, mac_address),
            )

    def list_devices(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM devices ORDER BY name COLLATE NOCASE")]

    def update_mac_address(self, device_id: str, mac_address: str | None) -> None:
        with self.connect() as db:
            db.execute("UPDATE devices SET mac_address=? WHERE device_id=?", (mac_address, device_id))

    def update_last_seen(self, device_id: str, timestamp: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE devices SET last_seen=? WHERE device_id=?", (timestamp, device_id))

    def remove_device(self, device_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM devices WHERE device_id=?", (device_id,))

    def rename_device(self, device_id: str, name: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE devices SET name=? WHERE device_id=?", (name, device_id))

    def log_event(self, *, device_id: str | None, device_name: str, action: str, status: str, details: str = "") -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit_log(device_id,device_name,action,status,details) VALUES(?,?,?,?,?)",
                (device_id, device_name, action, status, details),
            )

    def list_events(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (max(1, min(limit, 5000)),)
            )]

    def clear_events(self) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM audit_log")

    def integrity_check(self) -> list[str]:
        """Return SQLite integrity_check diagnostics (['ok'] for a healthy DB)."""
        with self.connect() as db:
            return [str(row[0]) for row in db.execute("PRAGMA integrity_check")]

    def backup_to(self, destination: str | Path) -> Path:
        """Create a consistent SQLite backup using SQLite's online backup API."""
        target = Path(destination)
        if target.resolve() == self.path.resolve():
            raise ValueError("Backup destination must differ from the live database")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = sqlite3.connect(target)
        try:
            with self.connect() as source:
                source.backup(backup)
            backup.execute("PRAGMA integrity_check")
            backup.commit()
        finally:
            backup.close()
        return target

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def get_settings(self) -> dict[str, str]:
        with self.connect() as db:
            return {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM settings")}
