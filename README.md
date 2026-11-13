# CENTRAL CUBE 1.0.0

CENTRAL CUBE — Windows desktop-приложение и отдельный агент для прямого управления компьютерами по взаимно аутентифицированному TLS (mTLS). Проект сохраняет устройства, настройки и журнал в SQLite. Облачный сервер не требуется.

> **Статус исходников:** версия 1.0.0. Функциональное ядро прошло автоматические проверки в доступной среде; Windows-бинарники и installer требуют отдельного фактического QA на Windows 10/11. Реальный mTLS-канал и одноразовое сетевое сопряжение проверены интеграционным тестом; удалённые Ping/System Information работают через контроллерский клиент, а Shutdown/Restart/Sleep поддерживаются агентом только при явном включении администратором и подтверждении в GUI. Сопряжение через одноразовый код работает после ручной выдачи mTLS-сертификата; автоматическая выдача сертификатов, Windows Service и готовые Windows EXE/Setup пока не поставляются. Не считать продукт production-ready до Windows QA и внешнего security review.

## Возможности

- PySide6 GUI: Dashboard, Devices, Bulk Actions (TCP-проверка и mTLS Ping для всех устройств), Reports, Guide, Settings, About.
- Добавление, переименование и удаление устройств; TCP reachability и last-seen.
- Удалённые команды Ping и System Information через mTLS.
- Shutdown/Restart/Sleep: выключены по умолчанию, требуют `--enable-power-actions` на агенте и отдельного подтверждения в GUI.
- TLS 1.2+, проверка CA, pinning SHA-256 сертификата агента и обязательный allowlist fingerprint клиентских сертификатов.
- Wake-on-LAN по MAC-адресу: отправка Magic Packet в локальный IPv4 broadcast; результат отправки не подтверждает включение ПК.
- Автозапуск приложения через HKCU Run на Windows; автозапуск агента при входе пользователя через PowerShell Scheduled Task scripts; отдельные скрипты создают/удаляют ограниченное правило Windows Firewall.
- JSONL audit log на агенте и SQLite audit log в контроллере.
- Ограничение размера протокольного кадра, тайм-ауты и отклонение повторного command ID в пределах процесса агента.

## Установка из исходников

```powershell
py -3.11 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m central_cube.main
```

## Агент и PKI

См. подробную процедуру выпуска сертификатов и настройки allowlist в [docs/AGENT_SETUP_RU.md](docs/AGENT_SETUP_RU.md). Кратко: агенту нужны server certificate/private key, CA сертификат клиентской PKI и обязательный JSON allowlist SHA-256 fingerprint доверенных клиентских сертификатов.

```powershell
central-cube-agent.exe --host 0.0.0.0 --port 9443 --cert agent.crt --key agent.key --client-ca centralcube-ca.crt --client-allowlist clients.json
```

Опасные действия выключены по умолчанию. Включать только осознанно:

```powershell
central-cube-agent.exe --host 0.0.0.0 --port 9443 --cert agent.crt --key agent.key --client-ca centralcube-ca.crt --client-allowlist clients.json --enable-power-actions
```

Не передавайте приватные ключи по почте или мессенджерам. Ограничьте доступ к ним Windows ACL. Для отзыва клиента удалите его fingerprint из allowlist и перезапустите агент.

## Сеть

- IPv4: нужен публичный WAN IPv4 и проброс одного входящего TCP-порта на агент.
- CGNAT/shared address space `100.64.0.0/10`: входящие IPv4-соединения обычно невозможны; запросите публичный IPv4 или используйте другой согласованный сетевой путь.
- IPv6: нужен глобальный IPv6 на целевом ПК и разрешающее правило Windows Firewall/роутера.
- Не публикуйте UDP broadcast и широкие диапазоны портов. Не отключайте firewall.
- Прямое соединение не гарантируется за NAT, CGNAT, корпоративным firewall или при динамическом адресе.

## Wake-on-LAN

Реализована отправка Magic Packet на локальный IPv4 limited broadcast UDP/9. Укажите MAC-адрес сетевой карты при добавлении устройства или при первом вызове WoL. Пакет не маршрутизируется через интернет, а успешная отправка не подтверждает включение. Возможность WoL зависит от BIOS/UEFI, NIC/драйвера, состояния питания и роутера. Не публикуйте UDP broadcast в интернет.

## Тесты и покрытие

```powershell
python -m pytest -q
```

Текущая автоматическая проверка: 53 теста успешно. Покрытие выбранного функционального ядра (agent commands/server, SQLite, pairing, network client/protocol, WoL) — 88%; UI и entrypoints в этот показатель не входят. PySide6 GUI не запускался в текущей среде.

## Сборка Windows

На Windows 10/11 x64 с Python 3.11+ запустите `scripts\\build_windows.bat`, затем соберите `installer\\CentralCube.iss` через Inno Setup 6. Сборка EXE/Setup в этой среде не выполнялась и не подтверждена. Перед распространением добавьте Authenticode-подпись и протестируйте на чистой Windows VM.

## Удаление

Удалите CENTRAL CUBE через «Параметры Windows → Приложения → Установленные приложения». Пользовательская SQLite-база оставляется для сохранения истории; удаляйте её отдельно только после резервного копирования.

## Документация

- [Установка](docs/INSTALL_RU.md)
- [Настройка агента и PKI](docs/AGENT_SETUP_RU.md)
- [Сеть и Wake-on-LAN](docs/NETWORK_AND_WOL.md)
- [Безопасность](docs/SECURITY_RU.md)
- [Устранение неполадок](docs/TROUBLESHOOTING_RU.md)
- [Статус реализации](docs/IMPLEMENTATION_STATUS_RU.md)
- [Архитектура](docs/ARCHITECTURE_RU.md)
- [Обновление](docs/UPDATE_RU.md)
- [Release Notes 1.0.0](docs/RELEASE_NOTES_1.0.0_RU.md)
- [Отчёт](WORK_REPORT_RU.md)
