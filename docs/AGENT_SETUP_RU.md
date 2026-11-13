# Настройка CentralCubeAgent

Агент запускает mTLS listener и требует:
- серверный сертификат и соответствующий приватный ключ;
- CA-сертификат, которым подписаны клиентские сертификаты контроллеров;
- доступный TCP-порт и разрешающее правило firewall.

## Проверенный mTLS канал (версия 0.1.4)

Агент теперь принимает один запрос на TLS-сессию, требует клиентский сертификат (`CERT_REQUIRED`), ограничивает команды allowlist, отклоняет повторный `command_id` в пределах текущего процесса и записывает события в JSONL audit log. Контроллер проверяет цепочку сервера через CA и дополнительно сравнивает SHA-256 fingerprint leaf-сертификата с записью устройства.

### Выдача сертификатов

Для эксплуатации используйте отдельный внутренний CA (лучше корпоративную PKI или офлайн CA). Пример ниже — схема с OpenSSL; выполняйте её на доверенном компьютере. CA private key не копируйте на управляемые ПК или контроллер.

```powershell
# 1) CA (создать один раз и хранить офлайн)
openssl genrsa -out centralcube-ca.key 4096
openssl req -x509 -new -key centralcube-ca.key -sha256 -days 3650 -out centralcube-ca.crt -subj "/CN=CentralCube Private CA"

# 2) Серверный сертификат агента (повторить на каждый агент; SAN должен содержать DNS/IP подключения)
openssl genrsa -out agent.key 3072
openssl req -new -key agent.key -out agent.csr -subj "/CN=centralcube-agent-host"
# Создать agent.ext с содержимым:
# subjectAltName=DNS:centralcube-agent-host,IP:192.0.2.10
# extendedKeyUsage=serverAuth
# keyUsage=digitalSignature,keyEncipherment
openssl x509 -req -in agent.csr -CA centralcube-ca.crt -CAkey centralcube-ca.key -CAcreateserial -out agent.crt -days 397 -sha256 -extfile agent.ext

# 3) Клиентский сертификат контроллера
openssl genrsa -out controller.key 3072
openssl req -new -key controller.key -out controller.csr -subj "/CN=centralcube-controller-01"
# Создать controller.ext с содержимым:
# extendedKeyUsage=clientAuth
# keyUsage=digitalSignature,keyEncipherment
openssl x509 -req -in controller.csr -CA centralcube-ca.crt -CAkey centralcube-ca.key -CAcreateserial -out controller.crt -days 397 -sha256 -extfile controller.ext
```

На агенте разместите `agent.crt`, `agent.key` и `centralcube-ca.crt` с ACL, разрешающими чтение только службе/администратору агента. На контроллере разместите `centralcube-ca.crt`, `controller.crt`, `controller.key`; приватный ключ не передавайте третьим лицам. Добавьте устройство, указав SHA-256 fingerprint DER-сертификата агента:

```powershell
openssl x509 -in agent.crt -outform DER -out agent.der
openssl dgst -sha256 agent.der
```

Создайте allowlist клиентских сертификатов. В него внесите SHA-256 fingerprint DER клиентского сертификата (без `sha256:`):

```powershell
openssl x509 -in controller.crt -outform DER -out controller.der
openssl dgst -sha256 controller.der
# Создать clients.json: ["<64 hex chars fingerprint>"]
```

Запуск агента (allowlist обязателен; без него доступ не будет выдан ни одному клиенту):

```powershell
central-cube-agent.exe --host 0.0.0.0 --port 9443 --cert agent.crt --key agent.key --client-ca centralcube-ca.crt --client-allowlist clients.json
```

Опасные команды по умолчанию выключены. Включать их можно только после оценки риска и настройки резервного сохранения данных:

```powershell
central-cube-agent.exe --host 0.0.0.0 --port 9443 --cert agent.crt --key agent.key --client-ca centralcube-ca.crt --client-allowlist clients.json --enable-power-actions
```

Контроллер в разделе Devices → «Удалённая команда» запросит CA, client certificate и client private key. Для Shutdown/Restart/Sleep появится отдельное подтверждение. Отказ агента, отключённые power actions или ошибки TLS будут отражены в журнале.

**Сопряжение:** при запуске агент печатает одноразовый шестизначный код (по умолчанию 300 секунд). В контроллере выберите устройство → «Сопряжение» и введите код из локальной консоли агента. Код одноразовый, допускает не более пяти неверных попыток; после успешного сопряжения SHA-256 fingerprint сертификата сохраняется в `clients.json`. Для добавления следующего нового контроллера перезапустите агент, чтобы получить новый код. Клиентский сертификат всё равно должен быть заранее выпущен доверенной CA; pairing не выпускает сертификаты и не передаёт приватные ключи. CRL/OCSP не реализованы; точечный отзыв клиента выполняется удалением его fingerprint из `clients.json` и перезапуском агента. Повторные `command_id` запоминаются в памяти процесса (до 10 000 последних ID), поэтому после перезапуска агента этот кеш очищается. Для продакшена используйте короткоживущие сертификаты, строгий контроль CA и ротацию при компрометации.

## Автозапуск агента при входе в Windows

Агент можно запускать как задачу Планировщика заданий текущего пользователя. Сначала проверьте, что ручной запуск с теми же аргументами работает, затем из PowerShell:

```powershell
.\scripts\install_agent_autostart.ps1 `
  -AgentExe "C:\Program Files\CENTRAL CUBE\Agent\CentralCubeAgent.exe" `
  -AgentArguments '--host 0.0.0.0 --port 9443 --cert "C:\CentralCube\agent.crt" --key "C:\CentralCube\agent.key" --client-ca "C:\CentralCube\centralcube-ca.crt" --client-allowlist "C:\CentralCube\clients.json"'
```

Удаление задачи:

```powershell
.\scripts\remove_agent_autostart.ps1
```

Это задача при входе пользователя, не Windows Service: агент не стартует до интерактивного входа. Храните ключи в каталоге с ограниченными ACL; учётная запись запуска должна иметь право чтения ключа и журнала.

## Windows Firewall

Для теста в доверенной локальной сети запустите PowerShell от имени администратора:

```powershell
.\scripts\install_agent_firewall.ps1 -Port 9443 -RemoteAddress LocalSubnet
```

Правило открывает только TCP/9443 для LocalSubnet и профилей Domain/Private; Public profile остаётся закрытым. Если требуется доступ из другой сети, задайте конкретный доверенный IP/CIDR через `-RemoteAddress`, а не `Any`. Удаление правила:

```powershell
.\scripts\remove_agent_firewall.ps1
```

Не создавайте правило на весь интернет без оценки экспозиции и реальной необходимости.
