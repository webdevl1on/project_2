# Промпт для Codex: Security 1.7 — доступ у локальній мережі (LAN)

> Скопіюйте все нижче лінії в Codex. Гілка: `feature/security`. Codex **не пушить**; коміт і пуш — після рев'ю.

---

## Контекст

Проєкт `project_2` (FastAPI + PostgreSQL, Windows). Працюєш у гілці `feature/security`. Дотримуйся `AGENTS.md`. Перед змінами прочитай лише:
- `docs/ARCHITECTURE.md` (таблиця «Навігація за завданням»),
- `docs/SECURITY.md` розділи «Центральний потік», «Доступні без входу винятки», «HTTPS і локальна розробка», «Конфігурація, backup та ротація ключів»,
- `docs/PRODUCTION_START.md`,
- код: `app/main.py`, `app/security/accounts.py` (`secure_transport`, перевірка Origin), `app/security/application.py`, `app/security/mfa_config.py` (`relying_party`), `app/database/settings.py` (`Settings.read`), `config/production.env.example`,
- тести: `tests/test_application_security.py` (зокрема `test_loopback_http_requires_explicit_flag_and_rejects_proxy_or_lan`), `tests/http_auth.py`.

Зараз сервер працює лише на `http://localhost:8000` (`PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1`). Потрібно дати доступ до 8 ПК у локальній мережі. Сервер — ПК з ім'ям Windows `foxlys`, адреса для всіх: **`https://foxlys.local:8443`** (ім'я знаходиться через mDNS Windows; роутер не налаштовуємо). Мережа/роутер можуть змінюватися — нічого не має залежати від конкретної IP-адреси чи підмережі.

## Мета

1. HTTPS прямо в uvicorn з сертифікатом від власного локального CA.
2. Мережевий фільтр: сервер обслуговує лише loopback і клієнтів з дозволених приватних підмереж.
3. Скрипти PowerShell для CA/сертифіката, клієнтських ПК, Firewall, Task Scheduler, резервного запису в `hosts`.
4. Тести й документація.

## Вимоги

### 1. Налаштування (розширити `app/database/settings.py` або окремий модуль `app/security/network.py`)

Нові змінні (документувати в `config/production.env.example` і `config/development.env.example`):
- `PROJECT2_SERVER_NAME` — DNS-ім'я, напр. `foxlys.local`. Обов'язкове, якщо `PROJECT2_BIND_HOST` не loopback.
- `PROJECT2_BIND_HOST` (типово `127.0.0.1`), `PROJECT2_PORT` (типово `8443` для LAN, `8000` для localhost).
- `PROJECT2_TLS_CERT`, `PROJECT2_TLS_KEY` — шляхи до PEM. Обов'язкові, якщо bind не loopback. Не можуть лежати в репозиторії, `static` чи сховищах даних.
- `PROJECT2_ALLOWED_NETWORKS` — `auto` (типово) або список CIDR через кому.
  - `auto`: приватні підмережі (IPv4 `is_private`, IPv6 `fe80::/10` і `fc00::/7`) активних мережевих інтерфейсів самого сервера. Обчислюються при старті й **перераховуються не частіше ніж раз на 60 с** (мережа могла змінитися). Для переліку інтерфейсів дозволено додати `psutil` з точною версією в `requirements.txt`.
  - Публічні (не приватні) адреси **ніколи** не дозволяються, навіть якщо задані явно → помилка конфігурації при старті.
  - Loopback дозволений завжди.
- Production: якщо bind не loopback, `PROJECT2_AUTH_ALLOW_LOCAL_HTTP` має бути вимкнений → інакше помилка старту.
- Узгодженість: `PROJECT2_WEBAUTHN_RP_ID` == `PROJECT2_SERVER_NAME`, а `PROJECT2_WEBAUTHN_ORIGINS` містить `https://<SERVER_NAME>:<PORT>` (або без порту для 443) → інакше помилка старту з зрозумілим текстом.

### 2. Мережевий фільтр (ASGI middleware у `app/main.py`)

- Діє на **кожен** запит, включно з `/static`, `/auth/login` і 404, **до** роутерів.
- IP клієнта — лише `scope["client"]` (TCP peer). Заголовки `Forwarded`, `X-Forwarded-*`, `X-Real-IP` тощо **ігноруються** для визначення IP (проксі немає). Наявна відмова на forwarded-заголовки в `secure_transport` залишається.
- Недозволений IP → 403 без тіла з даними, без cookie; подія в журнал застосунку (IP, шлях, без query string).
- Перевірка `Host`: дозволені лише `PROJECT2_SERVER_NAME`, а для loopback-клієнта ще `localhost`/`127.0.0.1`/`::1` (з портом або без). Інакше 400. Не використовуй `Host` для генерації абсолютних URL.
- Не послаблюй наявні перевірки: HTTPS обов'язковий для не-loopback (`secure_transport`), Origin/CSRF, cookie Secure/HttpOnly/SameSite=Strict, MFA.

### 3. Точка запуску `python -m app.serve`

- Читає `.env`/налаштування, валідує все з п.1, запускає `uvicorn.run(app, host, port, ssl_certfile, ssl_keyfile, proxy_headers=False, forwarded_allow_ips="", server_header=False, reload=False)`.
- Друкує стартовий рядок: адреса, режим мережі, дозволені підмережі. Секрети не друкує.
- `uvicorn app.main:app` напряму лишається для розробки на loopback.

### 4. PowerShell-скрипти в `scripts/lan/` (Windows PowerShell 5.1, без сторонніх утиліт)

Кожен скрипт: `[CmdletBinding()]`, `-WhatIf` де змінює систему, зрозумілі повідомлення українською, перевірка прав адміністратора там, де потрібно, ідемпотентність.

1. `New-Project2CA.ps1` — створює власний кореневий CA (RSA 3072 або ECDSA P-256, строк 10 років) і серверний сертифікат для `foxlys.local` (SAN: DNS `foxlys.local`, DNS `localhost`; EKU serverAuth; строк ≤ 825 днів). Використовує `New-SelfSignedCertificate`. Експортує в каталог поза репозиторієм (параметр, типово `C:\project2-secrets\tls\`): `project2-ca.cer` (публічний, для клієнтів), `server.crt.pem`, `server.key.pem`. Приватний ключ CA — лише в захищеному `.pfx` з паролем (запит через `Read-Host -AsSecureString`), не в PEM. NTFS ACL на каталог: лише поточний користувач + SYSTEM + Administrators. Друкує відбиток CA для звірки на клієнтах.
2. `Renew-Project2ServerCert.ps1` — перевипуск серверного сертифіката тим самим CA.
3. `Install-Project2ClientCA.ps1` — на клієнтському ПК (і на сервері): імпорт `project2-ca.cer` у `Cert:\LocalMachine\Root` з показом відбитка та підтвердженням.
4. `Set-Project2Firewall.ps1` — вхідне правило TCP на порт `PROJECT2_PORT` **лише для профілю Private**; попередження, якщо поточна мережа сервера має профіль Public (з підказкою `Set-NetConnectionProfile -NetworkCategory Private`). Перевіряє, що правило mDNS (UDP 5353) увімкнене для Private.
5. `Register-Project2Task.ps1` — задача Task Scheduler: запуск `<repo>\.venv\Scripts\python.exe -m app.serve` з робочим каталогом = корінь репозиторію, тригер «при старті системи», від указаного облікового запису Windows (не SYSTEM, з доступом до `.env`, TLS-ключа та каталогів даних), «Run whether user is logged on or not», `StartWhenAvailable`, `MultipleInstances IgnoreNew`, без ліміту часу, перезапуск при збої (3 спроби / 1 хв). Логи stdout/stderr — у файл поза репозиторієм з ротацією (простий підхід допустимий). Окремі параметри `-Unregister`, `-Status`.
6. `Add-Project2HostsEntry.ps1` — резервний варіант для клієнта, якщо mDNS не працює: додає/оновлює **один** рядок `<IP> foxlys.local # project2` у `hosts`, не чіпаючи інших рядків; `-Remove` видаляє лише його.
7. `Test-Project2Lan.ps1` — діагностика з клієнта: резолв `foxlys.local`, TCP до порту, TLS-ланцюжок довірений, HTTP-статус `/auth/login` = 200.

Скрипти не містять паролів, IP-адрес чи імен користувачів, окрім параметрів за замовчуванням `foxlys.local` та `8443`.

### 5. Тести (pytest, без реальної мережі)

- Мережевий фільтр: loopback дозволений; IP з дозволеної підмережі дозволений; чужа приватна підмережа → 403; публічна IP → 403; підробка `X-Forwarded-For` з дозволеною IP не допомагає; фільтр діє на `/static/...`, `/auth/login` і невідомий шлях.
- `Host`: `foxlys.local:8443` OK; чужий Host → 400; `localhost` від не-loopback клієнта → 400.
- `auto`: з підміненим переліком інтерфейсів — береться лише приватне, публічне ігнорується; кеш оновлюється після 60 с (керований час).
- Валідація налаштувань: bind не loopback без TLS/SERVER_NAME → помилка; публічний CIDR → помилка; невідповідність RP_ID/ORIGINS → помилка; `ALLOW_LOCAL_HTTP=1` з LAN-bind у production → помилка.
- `app.serve`: формує правильні аргументи `uvicorn.run` (підмінити `uvicorn.run`), `proxy_headers=False`.
- Наявні тести безпеки мають пройти без змін логіки (`tests/test_application_security.py`, `tests/test_mfa.py`, `tests/test_access_http.py`).
- PowerShell-скрипти: перевірка синтаксису, якщо доступний `pwsh` (`[System.Management.Automation.Language.Parser]::ParseFile`); якщо `pwsh` немає — чесно вкажи, що не перевірено.

Команди: `python -m pytest tests/ -q` на ізольованій SQLite (див. `docs/POSTGRESQL_SETUP.md`, «Тести»), а також релевантні тести на `project2_ci`, якщо PostgreSQL доступний. **Не запускай** `reset.py`, `reset_test_db.py`, кореневі `test*.py`.

### 6. Документація (українською, стисло)

- `docs/PRODUCTION_START.md` — новий розділ «Етап LAN»: порядок кроків на сервері (CA → сертифікат → `.env` → Firewall → задача → перевірка) і на кожному клієнті (встановити CA → `Test-Project2Lan.ps1` → вхід). Перехід з localhost: TOTP і резервні коди продовжують працювати; апаратні ключі/Windows Hello, зареєстровані для `localhost`, треба зареєструвати заново для `foxlys.local`. Що робити при зміні роутера/мережі (нічого, якщо профіль мережі Private і mDNS працює; інакше — `Add-Project2HostsEntry.ps1`). Строк сертифіката й перевипуск.
- `docs/SECURITY.md` — розділ «Security 1.7 — LAN»: модель загроз (чужа мережа, підробка Host/XFF, публічна мережа), що перевіряється і де.
- `docs/ARCHITECTURE.md` — рядок навігації та місце middleware у потоці запиту.
- `docs/CURRENT_STATE.md` — що реалізовано, що фактично перевірено, що **не** перевірено (реальні Windows-ПК, mDNS, Firewall, Task Scheduler, довіра до CA в браузерах).

## Межі

- Не змінюй моделі БД і міграції. Не змінюй логіку ролей, ACL, MFA, резервування.
- Не додавай реверс-проксі (Caddy/nginx/IIS) і NSSM.
- Не комітьте секрети, сертифікати, ключі, `.env`.
- Не роби `git push`. Наприкінці — локальний коміт у `feature/security` з повідомленням `feat(security): Security 1.7 LAN access over HTTPS`.

## Звіт наприкінці

Список змінених файлів; фактично запущені команди з результатами (passed/failed/skipped); що не перевірено і чому; відкриті питання.
