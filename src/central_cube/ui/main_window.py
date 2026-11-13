"""Functional desktop UI for managing the local device inventory and audit history."""
from __future__ import annotations

from central_cube import __version__

import csv
import json
import platform
import socket
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QInputDialog, QFileDialog,
)

from central_cube.core.database import Database

STYLESHEET = """
QMainWindow, QWidget { background: #071426; color: #E7F0FC; font-family: Segoe UI; font-size: 10pt; }
QFrame#Sidebar { background: #0B1B31; border-right: 1px solid #1B3554; }
QLabel#Brand { color: #F3F8FF; font-size: 17pt; font-weight: 700; letter-spacing: 2px; }
QLabel#Muted { color: #8FA7C3; }
QLabel#PageTitle { font-size: 22pt; font-weight: 650; }
QPushButton { background: #142B49; border: 1px solid #274568; border-radius: 8px; padding: 9px 13px; text-align: left; }
QPushButton:hover { background: #1B3A60; border-color: #5BA8E8; }
QPushButton:disabled { color: #60758d; background: #101f33; }
QListWidget, QTableWidget, QLineEdit, QComboBox { background: #0D2039; border: 1px solid #1B385A; border-radius: 7px; padding: 6px; }
QListWidget::item { padding: 11px; border-radius: 7px; margin: 2px 4px; }
QListWidget::item:selected { background: #193B62; }
QHeaderView::section { background: #142B49; padding: 7px; border: 0; }
QFrame#Panel { background: #0D2039; border: 1px solid #1B385A; border-radius: 14px; }
"""


class _WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _FunctionWorker(QRunnable):
    """Run a blocking operation outside the GUI thread."""
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _WorkerSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.function())
        except Exception as exc:  # surfaced in the GUI thread
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class DeviceDialog(QDialog):
    def __init__(self, parent=None, device=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить компьютер" if device is None else "Изменить компьютер")
        form = QFormLayout(self)
        self.name = QLineEdit(device["name"] if device else "")
        self.host = QLineEdit(device["host"] if device else "")
        self.port = QLineEdit(str(device["port"] if device else 9443))
        self.fingerprint = QLineEdit(device["fingerprint"] if device else "")
        self.fingerprint.setPlaceholderText("SHA-256 fingerprint сертификата агента")
        self.mac = QLineEdit((device.get("mac_address") or "") if device else "")
        self.mac.setPlaceholderText("AA:BB:CC:DD:EE:FF (необязательно, для WoL)")
        form.addRow("Название", self.name)
        form.addRow("IP / DNS", self.host)
        form.addRow("TCP-порт", self.port)
        form.addRow("TLS fingerprint", self.fingerprint)
        form.addRow("MAC (Wake-on-LAN)", self.mac)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        name, host, fp = self.name.text().strip(), self.host.text().strip(), self.fingerprint.text().strip()
        try:
            port = int(self.port.text())
        except ValueError as exc:
            raise ValueError("Порт должен быть числом.") from exc
        if not name or not host or not 1 <= port <= 65535 or not fp:
            raise ValueError("Заполните все поля; порт должен быть от 1 до 65535.")
        from central_cube.network.client import normalize_fingerprint
        normalize_fingerprint(fp)
        mac = self.mac.text().strip() or None
        if mac:
            from central_cube.network.wol import build_magic_packet
            build_magic_packet(mac)
        return name, host, port, fp, mac


class MainWindow(QMainWindow):
    NAV = ("Dashboard", "Devices", "Bulk Actions", "Reports", "Guide", "Settings", "About")

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self._checks_this_session = 0
        self._thread_pool = QThreadPool(self)
        self._active_workers = set()
        self.setWindowTitle("CENTRAL CUBE")
        self.resize(1280, 820)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(STYLESHEET)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(245)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 18)
        brand = QLabel("CENTRAL CUBE")
        brand.setObjectName("Brand")
        side.addWidget(brand)
        side.addSpacing(15)
        side.addWidget(QLabel("УСТРОЙСТВА"))
        self.device_list = QListWidget()
        self.device_list.itemSelectionChanged.connect(self._selection_changed)
        side.addWidget(self.device_list, 1)
        add = QPushButton("＋  Добавить компьютер")
        add.clicked.connect(self._add_device)
        side.addWidget(add)
        side.addSpacing(12)
        for index, label in enumerate(self.NAV):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, i=index: self._navigate(i))
            side.addWidget(button)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(28, 24, 28, 24)
        header = QHBoxLayout()
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("PageTitle")
        header.addWidget(self.page_title)
        header.addStretch(1)
        self.connection_label = QLabel("Локальный каталог устройств")
        self.connection_label.setObjectName("Muted")
        header.addWidget(self.connection_label)
        main.addLayout(header)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._dashboard())
        self.pages.addWidget(self._devices_page())
        self.pages.addWidget(self._bulk_page())
        self.pages.addWidget(self._reports_page())
        self.pages.addWidget(self._guide_page())
        self.pages.addWidget(self._settings_page())
        self.pages.addWidget(self._about_page())
        main.addWidget(self.pages, 1)
        layout.addWidget(sidebar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)
        self._refresh_devices()

    def _panel(self, title, description):
        panel = QFrame()
        panel.setObjectName("Panel")
        box = QVBoxLayout(panel)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        text = QLabel(description)
        text.setWordWrap(True)
        text.setObjectName("Muted")
        box.addWidget(heading)
        box.addWidget(text)
        return panel, box

    def _dashboard(self):
        page = QWidget()
        box = QVBoxLayout(page)
        panel, p = self._panel("Состояние устройств", "Сводка локального каталога. Сетевой статус определяется только фактическим ответом удалённого агента.")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        p.addWidget(self.summary)
        actions = QHBoxLayout()
        refresh = QPushButton("Обновить")
        refresh.clicked.connect(self._refresh_devices)
        actions.addWidget(refresh)
        actions.addStretch(1)
        p.addLayout(actions)
        box.addWidget(panel)
        box.addStretch(1)
        return page

    def _devices_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        panel, p = self._panel("Device Management", "Управление устройствами. Удалённые команды выполняются только через TLS с проверкой CA, клиентским сертификатом и сверкой SHA-256 fingerprint агента.")
        self.devices_table = QTableWidget(0, 6)
        self.devices_table.setHorizontalHeaderLabels(["Название", "Адрес", "Порт", "Fingerprint", "MAC", "Последнее подключение"])
        self.devices_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        p.addWidget(self.devices_table)
        row = QHBoxLayout()
        for label, callback in (("Добавить", self._add_device), ("Переименовать", self._rename_device), ("Удалить", self._remove_device), ("Проверить TCP", self._check_device), ("Сопряжение", self._pair_device), ("Удалённая команда", self._remote_command), ("Wake-on-LAN", self._wake_device)):
            b = QPushButton(label)
            b.clicked.connect(callback)
            row.addWidget(b)
        p.addLayout(row)
        box.addWidget(panel)
        return page

    def _bulk_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        panel, p = self._panel("Bulk Actions", "Массовая проверка TCP доступности. Массовые команды питания намеренно не включены: каждое опасное действие должно подтверждаться отдельно на устройстве.")
        self.bulk_status = QLabel("Проверка соединения не выполнялась.")
        p.addWidget(self.bulk_status)
        b = QPushButton("Проверить TCP для всех устройств")
        b.clicked.connect(self._bulk_check)
        p.addWidget(b)
        remote_ping = QPushButton("Ping всем сопряжённым устройствам (mTLS)")
        remote_ping.clicked.connect(self._bulk_remote_ping)
        p.addWidget(remote_ping)
        box.addWidget(panel)
        return page

    def _reports_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        panel, p = self._panel("История операций", "Журнал хранится в SQLite и сохраняется после перезапуска приложения.")
        self.events_table = QTableWidget(0, 5)
        self.events_table.setHorizontalHeaderLabels(["Дата", "Устройство", "Действие", "Статус", "Детали"])
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        p.addWidget(self.events_table)
        actions = QHBoxLayout()
        b = QPushButton("Обновить журнал")
        b.clicked.connect(self._refresh_events)
        actions.addWidget(b)
        export = QPushButton("Экспорт CSV")
        export.clicked.connect(self._export_events_csv)
        actions.addWidget(export)
        p.addLayout(actions)
        box.addWidget(panel)
        return page

    def _guide_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        panel, p = self._panel("Руководство", "1. Установите CENTRAL CUBE на управляющий ПК. 2. Установите CentralCubeAgent на целевой ПК. 3. Настройте сертификаты и сопряжение. 4. Добавьте адрес агента и сверенный TLS fingerprint. 5. Настройте входящий TCP firewall и, при необходимости, проброс одного TCP-порта.")
        for line in (
            "IPv4: требуется публичный WAN IPv4 и перенаправление TCP-порта на агент.",
            "CGNAT: входящие подключения IPv4 обычно невозможны; обратитесь к провайдеру за публичным адресом.",
            "IPv6: нужен глобальный адрес и разрешающее правило firewall.",
            "Не публикуйте UDP broadcast. Wake-on-LAN через интернет зависит от роутера.",
            "Для удалённых команд требуются CA, клиентский сертификат и приватный ключ, выданные администратором вашей PKI. Не пересылайте приватные ключи по почте или мессенджерам."
        ):
            label = QLabel("• " + line)
            label.setWordWrap(True)
            p.addWidget(label)
        box.addWidget(panel)
        return page

    def _settings_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        panel, p = self._panel("Настройки", "Параметры локального приложения сохраняются в SQLite.")
        self.startup = QComboBox()
        self.startup.addItems(["Не запускать вместе с Windows", "Запускать CENTRAL CUBE вместе с Windows"])
        try:
            from central_cube.core.startup import is_app_startup_enabled
            startup_enabled = is_app_startup_enabled()
        except OSError:
            startup_enabled = False
        self.startup.setCurrentIndex(1 if startup_enabled else 0)
        self.startup.currentIndexChanged.connect(self._set_app_startup)
        p.addWidget(QLabel("Автозапуск приложения (текущий пользователь Windows)"))
        p.addWidget(self.startup)
        note = QLabel("Автозапуск агента на управляемом ПК настраивается отдельно через scripts\\install_agent_autostart.ps1.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        p.addWidget(note)
        box.addWidget(panel)
        return page

    def _set_app_startup(self, index):
        enabled = bool(index)
        try:
            from central_cube.core.startup import set_app_startup
            set_app_startup(enabled)
            self.database.set_setting("startup", "1" if enabled else "0")
            self.statusBar().showMessage("Автозапуск обновлён", 5000)
        except OSError as exc:
            QMessageBox.warning(self, "Автозапуск недоступен", str(exc))
            self.startup.blockSignals(True)
            self.startup.setCurrentIndex(0 if enabled else 1)
            self.startup.blockSignals(False)

    def _about_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        panel, p = self._panel("CENTRAL CUBE", f"Версия {__version__} · Windows desktop controller. Прямое соединение без обязательного облака. Удалённые команды доступны при предварительной безопасной выдаче mTLS-сертификатов и настройке агента.")
        p.addWidget(QLabel("Локальные данные: SQLite\nПлатформа: " + platform.platform()))
        box.addWidget(panel)
        return page

    def _navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self.NAV[index])
        if index == 3:
            self._refresh_events()

    def _selected_id(self):
        items = self.device_list.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _refresh_devices(self):
        devices = self.database.list_devices()
        selected = self._selected_id()
        self.device_list.clear()
        for d in devices:
            item = QListWidgetItem("●  " + d["name"] + "\n    " + d["host"])
            item.setData(Qt.ItemDataRole.UserRole, d["device_id"])
            self.device_list.addItem(item)
            if d["device_id"] == selected:
                self.device_list.setCurrentItem(item)
        if hasattr(self, "summary"):
            self.summary.setText(f"Всего компьютеров: {len(devices)}\nПроверок в текущем сеансе: {self._checks_this_session}")
        if hasattr(self, "devices_table"):
            self.devices_table.setRowCount(len(devices))
            for r, d in enumerate(devices):
                vals = [d["name"], d["host"], str(d["port"]), d["fingerprint"], d.get("mac_address") or "—", d["last_seen"] or "—"]
                for c, value in enumerate(vals):
                    self.devices_table.setItem(r, c, QTableWidgetItem(value))

    def _selection_changed(self):
        device_id = self._selected_id()
        if not device_id:
            self.connection_label.setText("Локальный каталог устройств")
            return
        device = next((item for item in self.database.list_devices()
                       if item["device_id"] == device_id), None)
        if device is None:
            self.connection_label.setText("Устройство не найдено")
            return
        self.connection_label.setText(
            f"Выбрано: {device['name']} · {device['host']}:{device['port']}"
        )

    def _add_device(self):
        dialog = DeviceDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            name, host, port, fp, mac = dialog.values()
            import uuid
            self.database.add_device(device_id=str(uuid.uuid4()), name=name, host=host, port=port, fingerprint=fp, mac_address=mac)
            self.database.log_event(device_id=None, device_name=name, action="device_add", status="completed", details=f"{host}:{port}")
            self._refresh_devices()
        except Exception as exc:
            QMessageBox.warning(self, "Не удалось добавить устройство", str(exc))

    def _rename_device(self):
        device_id = self._selected_id()
        if not device_id:
            QMessageBox.information(self, "Устройство", "Сначала выберите компьютер в списке слева.")
            return
        d = next(x for x in self.database.list_devices() if x["device_id"] == device_id)
        name, ok = QInputDialog.getText(self, "Переименовать", "Новое название:", text=d["name"])
        if ok and name.strip():
            self.database.rename_device(device_id, name.strip())
            self.database.log_event(device_id=device_id, device_name=name.strip(), action="rename", status="completed")
            self._refresh_devices()

    def _remove_device(self):
        device_id = self._selected_id()
        if not device_id:
            QMessageBox.information(self, "Устройство", "Сначала выберите компьютер.")
            return
        d = next(x for x in self.database.list_devices() if x["device_id"] == device_id)
        if QMessageBox.question(self, "Удалить устройство", f"Удалить «{d['name']}» из каталога?") == QMessageBox.StandardButton.Yes:
            self.database.log_event(device_id=device_id, device_name=d["name"], action="device_remove", status="completed")
            self.database.remove_device(device_id)
            self._refresh_devices()

    def _start_worker(self, function, on_result, task_name="Операция", on_error=None):
        worker = _FunctionWorker(function)
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda result, w=worker: self._worker_finished(w, result, on_result))
        worker.signals.failed.connect(
            lambda error, w=worker: self._worker_failed(w, error, task_name, on_error)
        )
        self.statusBar().showMessage(f"{task_name}: выполняется…")
        self._thread_pool.start(worker)

    def _worker_finished(self, worker, result, callback):
        self._active_workers.discard(worker)
        callback(result)

    def _worker_failed(self, worker, error, task_name, on_error=None):
        self._active_workers.discard(worker)
        if on_error is not None:
            on_error(error)
        self.statusBar().showMessage(f"{task_name}: ошибка — {error}", 15000)
        QMessageBox.warning(self, task_name, error)

    def _select_mtls_files(self):
        """Collect all required mTLS files in the GUI thread, then persist paths."""
        settings = self.database.get_settings()
        paths = {}
        for key, caption, file_filter in (
            ("mtls_ca", "Выберите доверенный CA сертификат", "PEM (*.pem *.crt *.cer)"),
            ("mtls_cert", "Выберите клиентский сертификат", "PEM (*.pem *.crt *.cer)"),
            ("mtls_key", "Выберите клиентский приватный ключ", "PEM key (*.pem *.key)"),
        ):
            path, _ = QFileDialog.getOpenFileName(
                self, caption, settings.get(key, ""), file_filter
            )
            if not path:
                return None
            paths[key] = path
        for key, path in paths.items():
            self.database.set_setting(key, path)
        return paths

    def _check_device(self):
        device_id = self._selected_id()
        if not device_id:
            QMessageBox.information(self, "Проверка", "Выберите устройство.")
            return
        d = next(x for x in self.database.list_devices() if x["device_id"] == device_id)
        def check():
            started = datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                with socket.create_connection((d["host"], d["port"]), timeout=3):
                    return "reachable", "TCP-порт принимает соединения; TLS/идентичность не проверялись", started
            except OSError as exc:
                return "unreachable", str(exc), started
        def done(result):
            status, details, started = result
            self._checks_this_session += 1
            if status == "reachable":
                self.database.update_last_seen(device_id, started)
            self.database.log_event(device_id=device_id, device_name=d["name"], action="tcp_check", status=status, details=details)
            self.statusBar().showMessage(f"{d['name']}: {status} — {details}", 10000)
            self._refresh_devices()
            self._refresh_events()
        self._start_worker(check, done, "Проверка TCP")

    def _pair_device(self):
        device_id = self._selected_id()
        if not device_id:
            QMessageBox.information(self, "Сопряжение", "Выберите устройство в списке слева.")
            return
        d = next(x for x in self.database.list_devices() if x["device_id"] == device_id)
        code, ok = QInputDialog.getText(
            self, "Одноразовое сопряжение",
            "Введите 6-значный код, показанный в консоли агента:",
        )
        if not ok:
            return
        code = code.strip()
        if len(code) != 6 or not code.isdigit():
            QMessageBox.warning(self, "Сопряжение", "Код должен содержать ровно 6 цифр.")
            return
        paths = self._select_mtls_files()
        if paths is None:
            return

        def pair():
            from central_cube.network.client import pair_with_agent
            return pair_with_agent(
                d["host"], d["port"], ca_file=paths["mtls_ca"],
                client_cert=paths["mtls_cert"], client_key=paths["mtls_key"],
                fingerprint=d["fingerprint"], pairing_code=code, timeout=8,
            )

        def done(result):
            status = str(result.get("status", "unknown"))
            details = json.dumps(result, ensure_ascii=False)
            self.database.log_event(
                device_id=device_id, device_name=d["name"], action="pair",
                status=status, details=details[:4000],
            )
            QMessageBox.information(self, "Сопряжение", details[:6000])
            self._refresh_events()

        def failed(error):
            self.database.log_event(
                device_id=device_id, device_name=d["name"], action="pair",
                status="error", details=error[:4000],
            )
            self._refresh_events()

        self._start_worker(pair, done, "Сопряжение", on_error=failed)

    def _remote_command(self):
        device_id = self._selected_id()
        if not device_id:
            QMessageBox.information(self, "Удалённая команда", "Выберите устройство в списке слева.")
            return
        d = next(x for x in self.database.list_devices() if x["device_id"] == device_id)
        commands = ["ping", "system_info", "shutdown", "restart", "sleep"]
        labels = ["Ping", "System Information", "Shutdown", "Restart", "Sleep"]
        selected, ok = QInputDialog.getItem(
            self, "Удалённая команда", f"Устройство: {d['name']}\nКоманда:", labels, 0, False
        )
        if not ok:
            return
        command = commands[labels.index(selected)]
        confirmed = False
        if command in {"shutdown", "restart", "sleep"}:
            answer = QMessageBox.warning(
                self, "Опасное действие",
                f"Подтвердите {selected} на устройстве «{d['name']}».\n\n"
                "Операция может прервать работу и привести к потере несохранённых данных.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            confirmed = True
        paths = self._select_mtls_files()
        if paths is None:
            return

        def execute():
            from central_cube.network.client import send_command
            return send_command(
                d["host"], d["port"], ca_file=paths["mtls_ca"],
                client_cert=paths["mtls_cert"], client_key=paths["mtls_key"],
                fingerprint=d["fingerprint"], command=command,
                confirmed=confirmed, timeout=8,
            )

        def done(result):
            status = str(result.get("status", "unknown"))
            details = json.dumps(result, ensure_ascii=False)
            self.database.log_event(
                device_id=device_id, device_name=d["name"], action=command,
                status=status, details=details[:4000],
            )
            QMessageBox.information(self, "Ответ агента", details[:6000])
            self._refresh_events()

        def failed(error):
            self.database.log_event(
                device_id=device_id, device_name=d["name"], action=command,
                status="error", details=error[:4000],
            )
            self._refresh_events()

        self._start_worker(execute, done, f"Команда {selected}", on_error=failed)

    def _wake_device(self):
        device_id = self._selected_id()
        if not device_id:
            QMessageBox.information(self, "Wake-on-LAN", "Выберите компьютер в списке слева.")
            return
        d = next(x for x in self.database.list_devices() if x["device_id"] == device_id)
        mac = d.get("mac_address") or ""
        if not mac:
            mac, ok = QInputDialog.getText(self, "Wake-on-LAN", "MAC-адрес сетевой карты:")
            if not ok or not mac.strip():
                return
            mac = mac.strip()
            try:
                from central_cube.network.wol import build_magic_packet
                build_magic_packet(mac)
            except ValueError as exc:
                QMessageBox.warning(self, "Некорректный MAC", str(exc))
                return
            self.database.update_mac_address(device_id, mac)
        answer = QMessageBox.question(
            self, "Wake-on-LAN",
            f"Отправить Magic Packet для {d['name']} ({mac}) в локальную сеть?\n\n"
            "Пакет не маршрутизируется через интернет и не подтверждает, что ПК включился.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def wake():
            from central_cube.network.wol import send_magic_packet
            return send_magic_packet(mac)

        def done(sent):
            details = (
                f"Отправлено {sent} байт UDP broadcast на локальный broadcast port 9; "
                "запуск ПК не подтверждён"
            )
            self.database.log_event(
                device_id=device_id, device_name=d["name"], action="wake_on_lan",
                status="sent_unconfirmed", details=details,
            )
            QMessageBox.information(self, "Wake-on-LAN", details)
            self._refresh_events()

        def failed(error):
            self.database.log_event(
                device_id=device_id, device_name=d["name"], action="wake_on_lan",
                status="error", details=error[:4000],
            )
            self._refresh_events()

        self._start_worker(wake, done, "Wake-on-LAN", on_error=failed)

    def _bulk_remote_ping(self):
        devices = self.database.list_devices()
        if not devices:
            self.bulk_status.setText("Нет добавленных устройств.")
            return
        paths = self._select_mtls_files()
        if paths is None:
            return

        def ping_all():
            from central_cube.network.client import send_command
            results = []
            for device in devices:
                try:
                    response = send_command(
                        device["host"], device["port"], ca_file=paths["mtls_ca"],
                        client_cert=paths["mtls_cert"], client_key=paths["mtls_key"],
                        fingerprint=device["fingerprint"], command="ping", timeout=5,
                    )
                    status = str(response.get("status", "unknown"))
                    details = json.dumps(response, ensure_ascii=False)
                except Exception as exc:
                    status, details = "error", f"{type(exc).__name__}: {exc}"
                results.append((device, status, details))
            return results

        def done(results):
            lines = []
            for device, status, details in results:
                self.database.log_event(
                    device_id=device["device_id"], device_name=device["name"],
                    action="bulk_ping", status=status, details=details[:2000],
                )
                lines.append(f"{device['name']}: {status} — {details[:160]}")
            self.bulk_status.setText("\n".join(lines))
            self._refresh_events()

        self._start_worker(ping_all, done, "Массовый mTLS Ping")

    def _bulk_check(self):
        devices = self.database.list_devices()
        if not devices:
            self.bulk_status.setText("Нет добавленных устройств.")
            return
        def check_all():
            results = []
            for d in devices:
                started = datetime.now().astimezone().isoformat(timespec="seconds")
                try:
                    with socket.create_connection((d["host"], d["port"]), timeout=3):
                        status, details = "reachable", "TCP доступен; TLS не проверялся"
                except OSError as exc:
                    status, details = "unreachable", str(exc)
                results.append((d, status, details, started))
            return results
        def done(results):
            lines = []
            for d, status, details, started in results:
                self._checks_this_session += 1
                if status == "reachable":
                    self.database.update_last_seen(d["device_id"], started)
                self.database.log_event(device_id=d["device_id"], device_name=d["name"], action="bulk_tcp_check", status=status, details=details[:2000])
                lines.append(f"{d['name']}: {status} — {details[:160]}")
            self.bulk_status.setText("\n".join(lines))
            self._refresh_devices()
            self._refresh_events()
        self._start_worker(check_all, done, "Массовая проверка TCP")

    def closeEvent(self, event):
        # Do not destroy Qt objects while worker callbacks may still be queued.
        self._thread_pool.waitForDone(5000)
        if self._thread_pool.activeThreadCount():
            self.statusBar().showMessage("Ожидание завершения сетевых операций…")
            self._thread_pool.waitForDone()
        event.accept()

    def _refresh_events(self):
        if not hasattr(self, "events_table"):
            return
        events = self.database.list_events()
        self.events_table.setRowCount(len(events))
        for r, e in enumerate(events):
            vals = [e["created_at"], e["device_name"], e["action"], e["status"], e["details"]]
            for c, value in enumerate(vals):
                self.events_table.setItem(r, c, QTableWidgetItem(str(value)))

    def _export_events_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт журнала операций", "central_cube_report.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            from central_cube.core.reports import export_events_csv
            count = export_events_csv(self.database, path)
            self.database.log_event(
                device_id=None, device_name="CENTRAL CUBE", action="report_export",
                status="completed", details=f"CSV: {path}; строк: {count}",
            )
            QMessageBox.information(self, "Экспорт завершён", f"Экспортировано записей: {count}\n\n{path}")
            self._refresh_events()
        except (OSError, csv.Error) as exc:
            QMessageBox.warning(self, "Ошибка экспорта", str(exc))

