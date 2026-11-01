# Звіт переходу на PostgreSQL

Гілка `testing`, базовий commit перед змінами `5d67a64`. Робота без commit, push і merge; робоча SQLite та production не використовувалися. Детальні команди для Windows і обмеження — [POSTGRESQL_SETUP.md](POSTGRESQL_SETUP.md).

## Статус етапів

| Етап | Статус / результат |
| --- | --- |
| 0. Аудит | Завершено: SQLite-залежності розділені на runtime adapters, legacy-утиліти й portable ORM. Карта у SETUP. |
| 1. Підключення | Завершено: sync psycopg 3, явні mode/URL, pool/timeout/rollback/dispose, без fallback. |
| 2. ORM | Завершено: portable Boolean/CHECK, partial predicates для обох діалектів; дати, історія, revision збережені. |
| 3. Цілісність | Завершено: 48 таблиць, 3 EXCLUDE, 32 тригери, 58 додаткових constraints, штатні FK/UNIQUE/CHECK. |
| 4. Конкурентність | Завершено: row locks, revision, усі 8 погоджених паралельних сценаріїв, реальні HTTP 303/409, deadlock rollback, без небезпечного retry. |
| 5. Unicode / географія | Завершено для поточного переходу: нормалізація, aliases, рекурсивні запити, м'яка валідація, address/date parity; synthetic пошук 100k. Повний виробничий benchmark не виконувався. |
| 6. Alembic | Завершено: frozen initial, upgrade/current/history/check, startup read-only schema verification. Offline SQL/downgrade початкової схеми не підтримуються. |
| 7. Засівання | Завершено: references/names/geography/TCC/staff, read-only dry-run, repeat/conflict/rollback, без людей. |
| 8. Ізоляція | Завершено в коді/прикладах: prod/dev/ci, окремі шляхи, worktree інструкція. Реальні worktree/production сервер не створювалися. |
| 9. Production-безпека | Частково: startup відхиляє open/bypass/неповну конфігурацію. Legacy кадрові/staff маршрути ще потребують окремого загальносистемного контролю доступу; новий ACL виходить за межі завдання. Реальна експлуатація заблокована. |
| 10. Тести | Завершено: actual PostgreSQL integration, SQLite regression, Node/Chromium та PostgreSQL browser smoke. |
| 11. Backup / restore | Завершено для інфраструктури: реальний synthetic pg_dump/pg_restore в окрему БД перевірений. Процедура узгодженої копії приватних файлів описана; відновлення production-файлів не виконувалося. |
| 12. Windows-документація | Завершено: установка/ролі/БД/env/Alembic/seed/tests/worktree/два сервери/backup/restore. Самі Windows-команди в Codex не виконувалися. |
| 13. Підсумкова перевірка | Перехід для розробки перевірено. Production readiness залишається частковою через п.9; це не дозвіл завантажувати реальні персональні дані. |

## Фактично виконані перевірки

- Повний legacy/config Python-набір: **731 passed**, PostgreSQL tests skipped у цьому запуску. Два відомі попередження Starlette/httpx.
- Окремий PostgreSQL/config запуск: **41 passed**, із них **34 actual PostgreSQL**, **7 config**. Окремі схеми в project2_ci, PostgreSQL 17.
- Конкурентні сесії: посада/різні люди; одна людина/різні посади (також HTTP); один документ; активне ВЛК; автоматичні завдання; повторний імпорт; revision версії; порядок копій. Усі завершуються допустимим станом і контрольованою відмовою конкурента. Реальний deadlock окремо; serialization SQLSTATE тестується штучно викликаною помилкою БД.
- **43 Node**, **132 Chromium PASS** на legacy synthetic SQLite fixture; **5 Chromium PASS** сторінок реального PostgreSQL, без JS pageerror. Повного браузерного CRUD на PostgreSQL не запускали.
- Чиста PostgreSQL: Alembic upgrade/current/history/check, schema checker, seed dry-run/apply/repeat. Створено 43 довідникові записи, repeat — 0; людей 0. Наявні типи документів додаються міграцією окремо.
- pg_dump custom archive, pg_restore --list та реальне pg_restore --exit-on-error на іншому ізольованому PostgreSQL-сервері; schema checker, 21 звання / 8 типів документів / 0 людей.
- Географія: 100 000 synthetic GeoUnit, пошук префікса вкладається у тестовий поріг 5 с; це перевірка поточного тестового сервера, не SLA.

Нові залежності: psycopg[binary], Alembic, python-dotenv; httpx явно доданий для вже наявного FastAPI TestClient. requirements переведений з UTF-16 у UTF-8 для звичайного редагування. Сервіси й UI не переводилися на async або нові фреймворки.

Виправлення harness: явна testing/SQLite конфігурація для браузерного сервера та дочірніх Python-процесів; очищення cookies між suites, щоб адміністративна сесія попереднього сценарію не змінювала перевірку анонімного доступу наступного. Це не зміна авторизації застосунку.

## Створені та змінені файли

- `.env.example`
- `.gitignore`
- `alembic.ini`
- `app/database/db.py`
- `app/database/db_test.py`
- `app/database/init_db.py`
- `app/database/locking.py`
- `app/database/maintenance.py`
- `app/database/postgresql.py`
- `app/database/schema_check.py`
- `app/database/settings.py`
- `app/database/transactions.py`
- `app/models/documents.py`
- `app/models/geography.py`
- `app/models/medical.py`
- `app/models/mirage.py`
- `app/models/person_contact.py`
- `app/models/service_basis.py`
- `app/repositories/document_repository.py`
- `app/repositories/medical_repository.py`
- `app/repositories/person_repository.py`
- `app/repositories/position_table_repository.py`
- `app/repositories/profile_record_repository.py`
- `app/repositories/seed_repository.py`
- `app/repositories/staff_repository.py`
- `app/services/bootstrap_account.py`
- `app/services/dictionary_previews.py`
- `app/services/seed_geography.py`
- `app/services/seed_postgresql.py`
- `app/services/staff_service.py`
- `app/services/staff_tokens.py`
- `app/utils/date_query.py`
- `config/development.env.example`
- `config/production.env.example`
- `config/testing.env.example`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/DATABASE_RESET.md`
- `docs/DOCUMENTS.md`
- `docs/GEOGRAPHY.md`
- `docs/POSTGRESQL_REPORT.md`
- `docs/POSTGRESQL_SETUP.md`
- `docs/SERVICE_BASES.md`
- `docs/STAFF_HISTORY.md`
- `migrations/env.py`
- `migrations/script.py.mako`
- `migrations/sql/initial_catalog.sql`
- `migrations/sql/initial_functions.sql`
- `migrations/sql/initial_guards.sql`
- `migrations/sql/initial_schema.sql`
- `migrations/versions/0001_postgresql.py`
- `requirements.txt`
- `reset.py`
- `tests/browser/column_visibility.cjs`
- `tests/conftest.py`
- `tests/postgresql/conftest.py`
- `tests/postgresql/test_postgresql.py`
- `tests/test_database_settings.py`
