# Запуск робочої БД на Windows (етап «тільки сервер-ПК»)

Покрокова інструкція першого запуску production з нуля на ПК, який згодом стане LAN-сервером. Детальні пояснення — [POSTGRESQL_SETUP.md](POSTGRESQL_SETUP.md), безпека — [SECURITY.md](SECURITY.md), резервування — [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md).

На цьому етапі застосунок доступний **лише на самому сервер-ПК** (`http://localhost:8000`). Доступ інших ПК LAN (HTTPS, ім'я сервера, обмеження підмережі, служба Windows) — етап Security 1.7.

## 0. Передумови

- Windows 10/11 x64, Python 3.12+, Git, PostgreSQL **17** x64 з Command Line Tools (офіційний інсталятор).
- Під час встановлення PostgreSQL: порт 5432, `listen_addresses='localhost'` (типово). Пароль `postgres` збережіть у менеджері паролів.
- Робоча версія запускається з гілки `main` в **окремому каталозі** (не в тому, де ведеться розробка):

```powershell
git clone -b main https://github.com/webdevl1on/project_2 C:\project2-prod
cd C:\project2-prod
```

## 1. Python-середовище

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 2. Секрети

```powershell
python scripts/generate_production_secrets.py
```

Скрипт лише друкує значення: `STAFF_SIGNING_KEY`, `PROJECT2_MFA_KEYS`, пароль ролі БД. **Одразу збережіть їх офлайн** (менеджер паролів + зашифрований USB). Втрата `PROJECT2_MFA_KEYS` = неможливість входу з TOTP; втрата `STAFF_SIGNING_KEY` ламає перевірку підписаних даних. Ключі не змінюйте після старту без процедури ротації (SECURITY.md, «Конфігурація, backup та ротація ключів»).

## 3. Роль і БД PostgreSQL

```powershell
$env:Path = "C:\Program Files\PostgreSQL\17\bin;" + $env:Path
psql -h 127.0.0.1 -U postgres -d postgres -W
```

```sql
CREATE ROLE project2_prod LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password project2_prod
CREATE DATABASE project2_prod OWNER project2_prod ENCODING 'UTF8';
REVOKE ALL ON DATABASE project2_prod FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE project2_prod TO project2_prod;
\q
```

Для `\password` використайте пароль зі скрипта. Ролі `project2_dev`/`project2_ci` (розробка й тести) — за POSTGRESQL_SETUP.md, розділ «Windows 10».

## 4. Каталоги даних

```powershell
'documents','photos','temporary','exports','backups' | ForEach-Object { New-Item -ItemType Directory -Force -Path ("C:\project2-data\production\" + $_) | Out-Null }
```

Каталоги — поза репозиторієм. Рекомендовано диск із BitLocker.

## 5. Файл `.env`

```powershell
Copy-Item config/production.env.example .env
notepad .env
```

Замініть `CHANGE_ME` у `DATABASE_URL` паролем ролі, вставте `STAFF_SIGNING_KEY` і `PROJECT2_MFA_KEYS` зі скрипта. На етапі «тільки сервер-ПК»:

```
PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1
PROJECT2_WEBAUTHN_RP_ID=localhost
PROJECT2_WEBAUTHN_ORIGINS=["http://localhost:8000"]
```

`.env` ігнорується Git — не публікуйте його й не надсилайте в чат.

## 6. Схема, довідники, перший адміністратор

```powershell
python -m alembic upgrade head
python -m alembic current
python -c "from app.database.db import engine; from app.database.schema_check import require_current_schema; require_current_schema(engine); print('Schema OK'); engine.dispose()"
python -m app.services.mfa_keys --initialize
python -m app.services.seed_postgresql --dry-run --allow-production
```

`mfa_keys --initialize` — одноразовий запис контрольного значення ключа MFA; без нього сервер не стартує («Спочатку виконайте ... --initialize»). Повторний запуск лише перевіряє ключ.

Перегляньте звіт dry-run; якщо конфліктів немає — та сама команда без `--dry-run`. Додаткові джерела (`--names`, `--geography`, `--tcc`, `--staff-excel`) — POSTGRESQL_SETUP.md, «Безпечне засівання довідників».

```powershell
python -m app.services.bootstrap_account --username first-admin --display-name "Адміністратор"
```

Пароль запитується приховано. Bootstrap — **одноразово**; інших користувачів створює адміністратор у `/auth/users`.

## 7. Запуск і перший вхід

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Відкрийте саме `http://localhost:8000/persons` (не `127.0.0.1` — origin WebAuthn має збігатися з `.env`). Увійдіть і налаштуйте MFA.

**Важливо щодо MFA на цьому етапі:** використовуйте **TOTP** (застосунок-автентифікатор) і збережіть резервні коди. Апаратні ключі/Windows Hello, зареєстровані для `localhost`, не працюватимуть після переходу на LAN-ім'я в 1.7 — їх доведеться зареєструвати заново. TOTP і резервні коди переходять без змін.

## 8. Перевірка тестами (один раз, на тестовій БД)

Тести запускаються **не на production**: окрема роль/БД `project2_ci` і окремий `.env`/змінні процесу (POSTGRESQL_SETUP.md, «Тести»). Фікстури перестворюють таблиці тестової БД. Перед регулярною роботою прогніть PostgreSQL-набір на PostgreSQL 17 — у хмарному середовищі розробки 22 тести резервування/відновлення не були виконані через PostgreSQL 16, права CI-ролі та відсутній Chromium.

## 9. Резервування

До внесення значного обсягу даних налаштуйте резервні копії за [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md) і [SECURITY16_REPORT.md](SECURITY16_REPORT.md#налаштування-windows-перед-використанням): окремі keyring, `PROJECT2_BACKUP_CONFIG`, worker у Task Scheduler, перший реальний drill.

## Оновлення робочої версії

```powershell
cd C:\project2-prod
git pull origin main
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

Перед `upgrade` — свіжа перевірена резервна копія; сервер зупинений.
