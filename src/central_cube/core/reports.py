"""CSV report export helpers with spreadsheet-formula injection protection."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping, Any


EVENT_COLUMNS = (
    ("created_at", "Дата"),
    ("device_name", "Устройство"),
    ("action", "Действие"),
    ("status", "Статус"),
    ("details", "Подробности"),
)

DEVICE_COLUMNS = (
    ("device_id", "ID устройства"),
    ("name", "Название"),
    ("host", "Адрес"),
    ("port", "Порт"),
    ("fingerprint", "SHA-256 fingerprint"),
    ("mac_address", "MAC"),
    ("last_seen", "Последнее подключение"),
    ("created_at", "Создано"),
)


def _spreadsheet_safe(value: Any) -> str:
    """Neutralize cells that spreadsheet applications may interpret as formulas."""
    text = "" if value is None else str(value)
    probe = text.lstrip(" \t\r\n")
    if probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _write_csv(path: str | Path, rows: Iterable[Mapping[str, Any]], columns: tuple[tuple[str, str], ...]) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    # utf-8-sig makes the Russian headers display correctly in desktop Excel.
    with destination.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, dialect="excel", quoting=csv.QUOTE_MINIMAL)
        writer.writerow([label for _, label in columns])
        for row in rows:
            writer.writerow([_spreadsheet_safe(row.get(key)) for key, _ in columns])
            count += 1
    return count


def export_events_csv(database, path: str | Path, *, limit: int = 5000) -> int:
    """Export audit events in newest-first order; return the number of rows."""
    return _write_csv(path, database.list_events(limit=limit), EVENT_COLUMNS)


def export_devices_csv(database, path: str | Path) -> int:
    """Export the local device inventory; return the number of rows."""
    return _write_csv(path, database.list_devices(), DEVICE_COLUMNS)
