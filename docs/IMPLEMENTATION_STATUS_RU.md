# CENTRAL CUBE 1.0.0 — фактический статус

## Реализовано

- Сохранена исходная архитектура PySide6 / SQLite / asyncio.
- GUI: Dashboard, Devices, Bulk Actions (TCP checks), Reports, Guide, Settings, About.
- CRUD устройств, TCP reachability, last-seen и журнал SQLite.
- mTLS controller client с CA validation и pinning SHA-256 сертификата агента.
- Агент требует клиентский сертификат от указанной CA и сверяет fingerprint с обязательным allowlist.
- Удалённые Ping и System Information; power actions выключены по умолчанию и доступны только с флагом агента и отдельным подтверждением.
- JSONL audit log агента, SQLite audit log контроллера.
- Протокол с ограничением размера сообщения, тайм-аутом и атомарной SQLite-защитой от повтора command ID между конкурентными запросами и перезапусками.
- Оригинальный логотип подготовлен в PNG и ICO без изменения внешнего вида куба.
- Автозапуск приложения в HKCU Run и скрипты установки/удаления Scheduled Task для агента при входе пользователя. Это не Windows Service. Есть скрипты настройки ограниченного правила Windows Firewall для локальной сети.
- Wake-on-LAN: MAC хранится в SQLite; Magic Packet отправляется в локальный limited broadcast UDP/9; результат явно не трактуется как подтверждение включения.

## Проверки

- `pytest -q`: 38 passed.
- Интеграционный тест поднимает локальный mTLS listener, использует тестовые CA/server/client сертификаты и реально запрашивает system_info.
- `compileall`: успешно.
- Покрытие выбранного функционального ядра (agent commands/server, database, pairing, network client/protocol, WoL): 88%. UI и entrypoints в показатель не включены.
- PySide6 отсутствует в текущей среде; GUI не запускался. Windows EXE, Inno Setup, firewall, service install и multi-host QA не проверялись.

## Ограничения до production 1.0

- Одноразовый PairingCode интегрирован в сетевой mTLS enrollment и сохраняет fingerprint в allowlist; выпуск клиентского сертификата внешней PKI остаётся ручным.
- Нет CRL/OCSP; отзыв клиента реализован через fingerprint allowlist и требует перезапуска агента.
- Anti-replay store атомарно сохраняет последние 100 000 command ID в SQLite; политика длительного хранения требует эксплуатационной настройки.
- Нет Windows Service и системного трея; автозапуск агента доступен как Scheduled Task при интерактивном входе пользователя.
- Bulk Actions выполняет TCP-проверку и массовый read-only mTLS Ping; массовые power-команды намеренно не реализованы.
- GUI-сетевые вызовы синхронные и могут временно блокировать окно до сетевого тайм-аута.
- Нет >80% покрытия всего приложения; UI и entrypoints не включены в функциональное ядро 88%.
- Нет проверенной Windows сборки, Authenticode-подписи и внешнего security review.

Текущая версия — функциональная preview. Не распространять как production remote administration system без Windows QA, PKI lifecycle hardening и внешнего аудита.


## Дополнение — этап 3

- Агент ограничивает частоту запросов по IP token bucket: burst 20, refill 1 запрос/сек; таблица IP ограничена 4096 источниками.
- TLS handshake timeout: 10 секунд; TLS shutdown timeout: 5 секунд.
- Replay SQLite connections гарантированно закрываются.
- Linux tests: 44 passed; compileall passed; выборочное покрытие agent server/database/protocol — 88%.

- Добавлен программный отзыв клиентского сертификата с сохранением allowlist и audit event без обязательного перезапуска агента. Отзыв влияет на новые подключения; активные TLS-сессии не прерываются автоматически.


## Дополнение — этап 5 (отчёты и восстановление SQLite)

- Добавлен CSV-экспорт журнала операций из раздела Reports.
- Добавлены функции экспорта инвентаря устройств и журнала для повторного использования.
- CSV использует UTF-8 BOM для совместимости с Excel и экранирует потенциальные формулы (`=`, `+`, `-`, `@`) в пользовательских значениях.
- Добавлены `Database.integrity_check()` и `Database.backup_to()` на базе SQLite Online Backup API.
- Добавлены тесты экспорта, защиты от CSV formula injection, проверки целостности и восстановления из резервной копии.
- Linux pytest: 50 passed; compileall: passed.
- PySide6 GUI не запускался в этой среде; проверка визуального поведения экспорта и Windows-файлового диалога остаётся обязательной на Windows.

## Финальное состояние 1.0.0

После последующих этапов фоновые GUI-сетевые операции вынесены из основного потока, а отзыв сертификата применяется к новым подключениям без обязательного перезапуска агента. Единая release-версия обновлена до `1.0.0`.

Фактическая автоматическая проверка финального исходного дерева: `53 passed` и успешный `compileall`. Windows EXE/installer runtime QA по-прежнему требует запуска на реальной Windows и не считается выполненным только по наличию конфигураций сборки.
