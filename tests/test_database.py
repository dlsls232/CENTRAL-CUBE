from central_cube.core.database import Database


def test_device_and_audit_persistence(tmp_path):
    db = Database(tmp_path / "state.sqlite3")
    db.add_device(device_id="device-1", name="WORKSTATION-PC-01", host="192.0.2.10", port=9443, fingerprint="sha256:abc")
    db.log_event(device_id="device-1", device_name="WORKSTATION-PC-01", action="ping", status="completed")
    assert db.list_devices()[0]["name"] == "WORKSTATION-PC-01"
    assert db.list_events()[0]["action"] == "ping"
    db.rename_device("device-1", "Office PC")
    assert db.list_devices()[0]["name"] == "Office PC"
    db.remove_device("device-1")
    assert db.list_devices() == []


def test_settings_persist_across_instances(tmp_path):
    path = tmp_path / "state.sqlite3"
    Database(path).set_setting("startup", "1")
    assert Database(path).get_settings()["startup"] == "1"


def test_audit_log_survives_device_removal(tmp_path):
    db = Database(tmp_path / "state.sqlite3")
    db.add_device(device_id="d1", name="PC", host="localhost", port=9443, fingerprint="sha256:test")
    db.log_event(device_id="d1", device_name="PC", action="ping", status="completed")
    db.remove_device("d1")
    assert db.list_events()[0]["device_name"] == "PC"


def test_last_seen_is_persisted(tmp_path):
    db = Database(tmp_path / "state.sqlite3")
    db.add_device(device_id="d2", name="Laptop", host="127.0.0.1", port=9443, fingerprint="a" * 64)
    db.update_last_seen("d2", "2026-11-13T12:00:00+00:00")
    assert Database(tmp_path / "state.sqlite3").list_devices()[0]["last_seen"] == "2026-11-13T12:00:00+00:00"


def test_legacy_database_is_migrated_with_mac_column(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE devices (device_id TEXT PRIMARY KEY, name TEXT NOT NULL, host TEXT NOT NULL, port INTEGER NOT NULL, group_name TEXT, fingerprint TEXT NOT NULL, last_seen TEXT, wol_state TEXT NOT NULL DEFAULT 'unknown', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, device_id TEXT, device_name TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, details TEXT NOT NULL DEFAULT '')")
    finally:
        conn.close()
    db = Database(path)
    db.add_device(device_id="legacy", name="PC", host="127.0.0.1", port=9443, fingerprint="a" * 64)
    db.update_mac_address("legacy", "00:11:22:33:44:55")
    assert db.list_devices()[0]["mac_address"] == "00:11:22:33:44:55"


def test_event_report_csv_exports_russian_and_safe_cells(tmp_path):
    import csv
    from central_cube.core.reports import export_events_csv

    db = Database(tmp_path / "state.sqlite3")
    db.log_event(device_id=None, device_name="=HYPERLINK(\"https://bad.invalid\")",
                 action="ping", status="completed", details="  +SUM(1,1)")
    output = tmp_path / "exports" / "events.csv"
    assert export_events_csv(db, output) == 1
    with output.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["Дата", "Устройство", "Действие", "Статус", "Подробности"]
    assert rows[1][1].startswith("'=HYPERLINK")
    assert rows[1][4].startswith("'  +SUM")


def test_device_report_csv_exports_inventory(tmp_path):
    import csv
    from central_cube.core.reports import export_devices_csv

    db = Database(tmp_path / "state.sqlite3")
    db.add_device(device_id="device-1", name="Office PC", host="192.0.2.2",
                  port=9443, fingerprint="a" * 64)
    output = tmp_path / "devices.csv"
    assert export_devices_csv(db, output) == 1
    with output.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["Название"] == "Office PC"
    assert rows[0]["Порт"] == "9443"


def test_sqlite_integrity_check_and_online_backup(tmp_path):
    import sqlite3
    source_path = tmp_path / "live.sqlite3"
    db = Database(source_path)
    db.add_device(device_id="backup-device", name="Backup PC", host="127.0.0.1",
                  port=9443, fingerprint="b" * 64)
    db.log_event(device_id="backup-device", device_name="Backup PC",
                 action="test", status="completed")
    assert db.integrity_check() == ["ok"]

    backup_path = db.backup_to(tmp_path / "backups" / "snapshot.sqlite3")
    restored = Database(backup_path)
    assert restored.list_devices()[0]["device_id"] == "backup-device"
    assert restored.list_events()[0]["action"] == "test"
    assert restored.integrity_check() == ["ok"]

    from contextlib import closing
    with closing(sqlite3.connect(backup_path)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_sqlite_backup_rejects_overwriting_live_database(tmp_path):
    import pytest
    db = Database(tmp_path / "live.sqlite3")
    with pytest.raises(ValueError, match="differ"):
        db.backup_to(db.path)
