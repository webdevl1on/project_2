# PostgreSQL та Alembic

Цільова СУБД — PostgreSQL **17**, синхронний psycopg 3 / SQLAlchemy. SQLite залишається лише для явних legacy-утиліт і наявних тестів. Перенесення старих персональних даних не реалізоване й автоматично не виконується.

Security 1.1–1.3 забезпечують персональний вхід, MFA, CSRF і сесії 15 хв / 8 год. Security 1.4 додає scoped ACL поверх організаційної структури. Поточний head — **0010_organization_hierarchy**, після 0009; див. [SECURITY.md](SECURITY.md) та [ACCESS_CONTROL.md](ACCESS_CONTROL.md).

`0010_organization_hierarchy` додає рівень other, нові види та основну ієрархію; [ORGANIZATION.md](ORGANIZATION.md). Старі other залишають NULL. Старі зворотні/однакові рівні відомих типів блокують upgrade з ID проблеми; виправте підпорядкування явно старим інтерфейсом до міграції. Відмова відкочує DDL і не змінює даних. Перед ручним upgrade — перевірений backup. Ревізія застосовувалася тут лише до ізольованих випадкових схем project2_ci, не dev/prod. Reset не потрібний.


Security 1.5 додає [узгоджені зашифровані резервні копії й ізольоване відновлення](BACKUP_AND_RESTORE.md), без нової Alembic-ревізії. `testing` дозволяє також явно створені `project2_restore_<hex>` для запуску відновленої копії; pytest, seed і робочі середовища зберігають свої окремі обмеження.

Перед ручним upgrade: перевірений backup БД/сховища та окремий backup MFA-ключів, доступ чинного Master і окремого Admin з MFA. `python -m alembic current` / `python -m alembic heads`, потім за окремим рішенням — `python -m alembic upgrade head`. Editor/Viewer стають User **без автоматичних предметних прав**; матриці потрібно явно налаштувати на `/admin/access`. Master не має автоматичного доступу до персональних даних; Admin має. ID, паролі, MFA, сесії й журнали зберігаються. Нові ACL-таблиці/unique User–Person/guards перевіряє schema checker. Startup не мігрує; reset не потрібний. Перевірки нового етапу виконуються тільки у випадкових схемах `project2_ci`, без використання dev/prod.

## Межі й карта аудиту

| Залежність | Рішення |
| --- | --- |
| `database/db.py`, прихований `sqlite:///...` | `Settings`: обов'язкові `PROJECT2_ENV`, `DATABASE_URL`, без fallback. |
| `models/*`: `sqlite_where`, Boolean `=1`, сума Boolean | Додані `postgresql_where`, portable true/false, CASE для кількості власників. Семантика історії збережена. |
| `models/staff.py`, `models/documents.py`, `models/medical.py`, `database/*_schema.py` | SQLite-реалізації залишені; PostgreSQL-еквіваленти зафіксовані в `migrations/sql/initial_guards.sql`. |
| `BEGIN IMMEDIATE` в `staff_service.write_unit`, `service_transaction` | Лише SQLite. PostgreSQL: блокування конкретних рядків, revision, UNIQUE та EXCLUDE. |
| SQLite UDF `unicode_contains`, `formatted_address`, `project2_date_match` | PostgreSQL-функції в початковій Alembic-міграції; DateBinding обирає діалект. |
| `PRAGMA`, `sqlite_master`, sqlite3 backup, rebuild міграцій | Тільки legacy SQLite-ініціалізація, перевірка схеми, `migrate_*.py`, `database_reset`, тести. Не застосовуються до PostgreSQL. |
| `init_db` / `reset.py` | Відмовляють для PostgreSQL; reset також заборонений у production. Старі SQLite-міграції не видалені. |
| `seed_bootstrap`, `seed_all`, `seed_test_people`, `dev_auth` CLI | Залишені як явні SQLite-інструменти. Новий PostgreSQL seed працює окремо й не створює людей. |
| SQLAlchemy repositories, Router → Service → Repository | Збережені. Сесії передаються ззовні, repository не виконує commit. |
| Тести `db_test.py`, `tests/conftest.py` | Тимчасові SQLite-файли, лише testing. PostgreSQL — окремий fixture з перевіркою `project2_ci` та випадковою схемою на кожний тест. |

## Конфігурація і зберігання

| Режим | Гілка / БД | Сервер |
| --- | --- | --- |
| development | `testing` / `project2_dev` | 127.0.0.1:8001, reload дозволений |
| production | майбутній `main` / `project2_prod` | 127.0.0.1:8000, без reload |
| testing | `project2_ci` | pytest; окремі тимчасові схеми |

Приклади: [.env.example](../.env.example), [development](../config/development.env.example), [production](../config/production.env.example), [testing](../config/testing.env.example). Справжні `.env` і `data/` ігноруються Git. `PROJECT2_ENV_FILE` дозволяє обрати інший файл; чинні змінні процесу мають пріоритет над dotenv.

`Settings` забороняє development → prod, testing → dev/prod і production → іншу БД. Для production обов'язкові PostgreSQL, авторизація `PROJECT2_AUTH_ENABLED=1`, відсутність dev bypass, стабільний `STAFF_SIGNING_KEY` довжиною 32+ символи та п'ять незалежних каталогів. Каталоги не можуть збігатися або бути вкладеними один в одного.

`PROJECT2_DOCUMENT_STORAGE`, `PROJECT2_PHOTO_STORAGE`, `PROJECT2_TEMP_STORAGE`, `PROJECT2_EXPORT_STORAGE`, `PROJECT2_BACKUP_STORAGE` розділені за середовищами. Сховище документів лишається чинним захищеним файловим API; BLOB у БД не додаються. Поле фото поки не має окремого механізму завантаження: для майбутнього заданий незалежний шлях. Облікові записи ОС / NTFS ACL також повинні забороняти development доступ до production-каталогів; самої перевірки шляхів недостатньо для цього.

Пул за замовчуванням 5 з'єднань + 5 overflow на процес, очікування 20 с, pre_ping; змінні `PROJECT2_POOL_SIZE`, `PROJECT2_MAX_OVERFLOW`, `PROJECT2_POOL_TIMEOUT`. Connect timeout 10 с, lock timeout 10 с, statement timeout 120 с. Сесія закривається в `get_db`, помилка викликає rollback, завершення сервера — engine.dispose().

## Windows 10: встановлення і створення БД

Встановіть PostgreSQL 17 x64 офіційним інсталятором, включно з Command Line Tools. Пароль адміністратора задайте самостійно, не зберігайте його в репозиторії. Не відкривайте порт у LAN: локальному серверу достатньо loopback. У postgresql.conf залиште listen_addresses='localhost', а pg_hba.conf — лише потрібні loopback-правила з парольним входом; після зміни перезапустіть службу.

У PowerShell з кореня потрібного worktree:

```powershell
$env:Path = "C:\Program Files\PostgreSQL\17\bin;" + $env:Path
psql --version
pg_dump --version
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
psql -h 127.0.0.1 -U postgres -d postgres -W
```

У відкритому psql виконайте **один раз**. Це явна адміністративна дія; застосунок БД та ролі не створює. `\password` вводить пароль без включення його до командного рядка:

```sql
CREATE ROLE project2_prod LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password project2_prod
CREATE ROLE project2_dev LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password project2_dev
CREATE ROLE project2_ci LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password project2_ci
CREATE DATABASE project2_prod OWNER project2_prod ENCODING 'UTF8';
CREATE DATABASE project2_dev OWNER project2_dev ENCODING 'UTF8';
CREATE DATABASE project2_ci OWNER project2_ci ENCODING 'UTF8';
REVOKE ALL ON DATABASE project2_prod FROM PUBLIC;
REVOKE ALL ON DATABASE project2_dev FROM PUBLIC;
REVOKE ALL ON DATABASE project2_ci FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE project2_prod TO project2_prod;
GRANT CONNECT, TEMPORARY ON DATABASE project2_dev TO project2_dev;
GRANT CONNECT, TEMPORARY ON DATABASE project2_ci TO project2_ci;
\q
```

Ролі-власники можуть виконувати Alembic у власній БД. Для експлуатації з реальними даними доцільно відокремити роль міграцій від runtime з мінімальними правами; у цьому завданні повний operational hardening не реалізований. Розширення `btree_gist` входить до PostgreSQL і є trusted; якщо права керованого сервера забороняють його створення, адміністратор встановлює його окремо у потрібній БД.

```powershell
psql -h 127.0.0.1 -U project2_dev -d project2_dev -W -c "SELECT current_database(), current_user, version();"
if (-not (Test-Path .env)) { Copy-Item config/development.env.example .env }
notepad .env
```

Створіть файлові каталоги обраного середовища (приклад development):

```powershell
'documents','photos','temporary','exports','backups' | ForEach-Object { New-Item -ItemType Directory -Force -Path ("C:\project2-data\development\" + $_) | Out-Null }
```

У `.env` замініть `CHANGE_ME`, перевірте всі шляхи та встановіть власний випадковий STAFF_SIGNING_KEY. Спеціальні символи пароля в URL мають бути percent-encoded. Не публікуйте `.env`, повний URL або вивід із паролями. Для psql/pg_dump/pg_restore можна використовувати Windows `%APPDATA%\postgresql\pgpass.conf` з правами лише власника; не додавайте пароль до аргументів команд.

## Alembic: порожня БД і перевірка схеми

```powershell
python -m alembic history
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -c "from app.database.db import engine; from app.database.schema_check import require_current_schema; require_current_schema(engine); print('Schema OK'); engine.dispose()"
```

Початкова ревізія `0001_postgresql` створює **48 предметних таблиць**, індекси й каталог типів документів; `alembic_version` — додаткова службова таблиця. Заморожені SQL-снапшоти не імпортують живі моделі для створення таблиць.

- Три GiST exclusion constraints захищають включені періоди версій, зайнятості посади та людини. NULL завершення означає відкритий період до граничної дати чинної моделі.
- 32 тригери захищають межі версій, історію призначень, власників і заміну документів, append-only аудит, ВЛК, завдання та зв'язки документів.
- 58 додаткових constraints включають ці EXCLUDE, календарні компоненти, точні Date та узгодженість Date-проєкцій. Також встановлені FK/CHECK/UNIQUE зі снапшота ORM і часткові UNIQUE.
- Функції Unicode, форматування адрес та possible-match дат встановлюються тією ж ревізією.

Startup лише читає схему: перевіряє ревізію, таблиці/колонки, наявність guard constraints, увімкнені тригери, функції та предикати часткових індексів. Не запускає create_all, upgrade або seed. Зміна тіла функції чи виразу constraint під тим самим ім'ям потребує додаткового ручного аудиту; перевірка наявності не є повним криптографічним порівнянням DDL.

Майбутні зміни: нова Alembic-ревізія, перевірений SQL для тригерів/функцій, оновлення expected head у schema checker і тести на порожній та попередній схемі. Autogenerate не замінює ручної перевірки цих об'єктів. `alembic check` перевіряє metadata drift; додаткові guard-об'єкти перевіряє schema checker. Початковий downgrade навмисно відмовляє у видаленні всіх таблиць: відновлення — з перевіреного backup. Offline `upgrade --sql` не підтримується цією початковою ревізією; виконувати online upgrade на явно обраній БД.

Для обов’язкового персонального входу створіть першого адміністратора окремою явною командою, після міграції:

```powershell
python -m app.services.bootstrap_account --username first-admin --display-name "Адміністратор"
```

Пароль вводиться через прихований prompt, не через аргументи. Наступні облікові записи створює персональний admin через /auth/users. Старі token-admin/dev bypass не авторизують запит; схема та міграції БД для Security 1.1 не змінені.

## Транзакції і конкурентність

Сервіс володіє commit/rollback; repository не робить commit. `commit=False`/зовнішня Session дозволяє спільну атомарну операцію. SQLite `BEGIN IMMEDIATE` збережений лише в legacy-адаптері.

PostgreSQL використовує READ COMMITTED, `SELECT FOR UPDATE` при write-читанні Person/документа/версії/медичного запису, revision та обмеження БД. Тригер призначення бере SHARE на версію; вибір активного ВЛК — SHARE на довідку. Незалежні люди й документи не блокують усю БД. Advisory lock застосовується лише для взаємної синхронізації CLI-засівань.

SQLSTATE 40001, 40P01, 55P03 перетворюються на контрольовану відмову з rollback; StaffService також обробляє exclusion/UNIQUE/revision. Автоматичних повторів операції немає. Після відмови користувач оновлює дані й явно повторює дію. Прямий SQL також обмежений EXCLUDE/UNIQUE/guards.

HistoryModel лишається точним DateTime з чинною UTC-семантикою; тип SQL — timestamp without time zone, як у поточній ORM. З'єднання примусово використовує UTC. Предметний Date не зміщується часовими поясами; PersonEvent та штатні періоди залишаються точними. Неповні дати не доповнюються вигаданими компонентами.

## Безпечне засівання довідників

Новий CLI не викликає reset, міграції або seed_test_people. Починайте з preview:

```powershell
python -m app.services.seed_postgresql --dry-run
python -m app.services.seed_postgresql
```

Додаткові джерела задаються явно, без припущень про наявність локальних файлів:

```powershell
python -m app.services.seed_postgresql --dry-run --names "C:\seed\names" --geography "C:\seed\geography" --tcc "C:\seed\tcc.xlsx" --staff-excel "C:\seed\reference_data.xlsx" --version-name "Тестовий штат" --valid-from 2026-01-01
```

Після перегляду звіту приберіть `--dry-run`, зберігши решту аргументів. `--names` приймає перевірений пакет або один чинний шестилистовий XLSX; географія — пакет із manifests/SHA256; ТЦК — чинний шаблон; штат — тільки positions із чинними назвами колонок. Для архівного штату додайте `--valid-to YYYY-MM-DD`.

Dry-run використовує read-only транзакцію: не записує рядків, квитанцій або sequence. Звіт містить new/existing/conflicts/errors і компоненти. Apply — одна транзакція; будь-який конфлікт чи помилка відкатує весь набір. Наявний запис порівнюється за стабільним ключем; відмінності не перезаписуються, навіть якщо це ручна зміна. Географічні коди/UUID не замінюються випадковими значеннями. Новий штат вакантний; жодних призначень, людей, медичних даних чи копій документів CLI не створює.

Для production навіть dry-run вимагає явного `--allow-production`; **у межах цього завдання його не запускати**. Вирішення конфліктів виконується окремо після перевірки джерела, без автоматичного overwrite. Старі SQLite reset/seed-команди описані в [DATABASE_RESET.md](DATABASE_RESET.md).

## Тести

Виконуйте з кореня testing worktree. Не задавайте production/dev URL для тестів:

```powershell
$env:PROJECT2_ENV = "testing"
$env:DATABASE_URL = "postgresql+psycopg://project2_ci:CHANGE_ME@127.0.0.1:5432/project2_ci"
$env:PROJECT2_TEST_DATABASE_URL = $env:DATABASE_URL
python -m pytest tests/postgresql/ tests/test_database_settings.py -q
node --test tests/js/*.test.cjs
```

PostgreSQL fixture перевіряє **саме project2_ci** до DDL, створює випадкову `project2_test_<uuid>` схему, застосовує Alembic й видаляє лише власну схему. Локальна alembic_version створюється явно, щоб версія з public не спричинила пропуск міграції. Для CI потрібні права CREATE SCHEMA/EXTENSION у власній БД. Не запускайте паралельно вебсервер на цих тимчасових схемах.

Legacy regression запускається з явною ізольованою SQLite, без впливу на .env:

```powershell
Remove-Item Env:PROJECT2_TEST_DATABASE_URL -ErrorAction SilentlyContinue
$env:DATABASE_URL = "sqlite:///$env:TEMP/project2-legacy-app.sqlite3"
python -m pytest tests/ -q
```

Браузерний harness сам використовує тимчасову SQLite і synthetic fixtures; його успіх не є PostgreSQL-доказом:

```powershell
npm install --no-save playwright
npx playwright install chromium
$env:PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
node tests/browser/column_visibility.cjs
```

Потрібні Node і curl, Bootstrap завантажується для ізольованого перехоплення CDN у браузері. `COLUMN_STAGE` дозволяє вибрати існуючий окремий suite, наприклад medical, staff, history_forms, document_ui.

## Два worktree і сервери

Нижче — майбутнє налаштування користувачем; Codex не створює worktree і не змінює main:

```powershell
git worktree add ..\project2-prod main
```

Чинний testing-каталог лишається development. У кожному каталозі окремі venv і `.env`; у prod скопіюйте production.env.example, у testing — development.env.example. Різні ролі PostgreSQL і NTFS-каталоги обов'язкові. Не припускайте, що main вже містить ці зміни: перенесення коду потребує окремого погодженого release.

Production-конфігурація (наступні етапи ACL/2FA ще не завершені):

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Development, інше вікно PowerShell та testing-каталог:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Зупинка — Ctrl+C. Не використовуйте `--reload` для production. Налаштування не відкриває LAN.

## Резервна копія та перевірене відновлення

Поточна процедура Security 1.5 — [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md): зашифрований узгоджений PostgreSQL snapshot + документи/фото, незалежно зашифрована капсула критичних MFA/signing/RP-параметрів, маніфест і перевірка кожного файла. Старе незалежне `pg_dump` + `Copy-Item` активного каталогу не є повним узгодженим backup і більше не є рекомендованою процедурою.

Потрібні PostgreSQL client tools **17**, приватний зашифрований staging, два окремі keyring поза Git/backup, явний `PROJECT2_BACKUP_CONFIG`, чинний deployment release та OS-планувальник. Для самого модуля резервування нової Alembic-ревізії не додавалося (етап на 0009); поточний head після виправлень ієрархії — **0010_organization_hierarchy**. Жодна робоча БД автоматично не змінюється.

```powershell
$env:PROJECT2_ENV_FILE = 'C:\project2-secrets\backup.env'
.venv\Scripts\python.exe -m app.services.backup create
.venv\Scripts\python.exe -m app.services.backup verify --id <ID_КОПІЇ>
```

Команди запитують чинну Master-сесію зі свіжою MFA через прихований prompt. Щоденні full та самодостатні точки кожні 30 хвилин робить системний worker, а не сторінка браузера. `/admin/backups` показує стан Master/Admin; критичні запуски доступні Master. RPO ≤1 година залежить від фактичного інтервалу успішних snapshot, а для втрати майданчика — перевірених зовнішніх реплік.

Відновлення лише до **нової порожньої** `project2_restore_<hex>` на ізольованому PostgreSQL: підписаний plan, preview, підтвердження, `pg_restore --single-transaction`, schema/row/file/MFA checks, staged files. Без `--clean` і без HTTP restore. Старі сесії відновленої копії відкликаються; source не змінюється. `PROJECT2_ENV=testing` дозволяє запуск цієї ізольованої копії з незалежними каталогами; pytest дозволений як і раніше тільки у project2_ci. Робоче перемикання — окреме ручне вікно з попереднім цілим rollback-комплектом, описане в runbook.

Повна інструкція Windows/Linux, external marker, retention/quota, escrow/rotation, аварійне підтвердження Master та регулярні дозволені CI drills — [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md). Автоматичні reset, міграції чи production restore не запускаються.

## Відомі прогалини і діагностика

- Захист документів/медичних API та персональні сесії збережені. Але `/persons` (читання/запис), `/events` і його read API, `/person-positions`, `/staff/*` (включно з історичними й адміністративними POST), `/persons/...` контакти/адреси/хронологія/підстави служби та старі ПІБ/звання ще не мають єдиного обов'язкового current_user/ACL. Захищена сторінка `/admin/staff` не захищає старі прямі staff POST. Потрібен окремий загальносистемний етап; тут ролі не змінювалися.
- Windows-команди задокументовані, але виконані перевірки Codex — Linux / PostgreSQL 17 / Chromium. Інсталяція PostgreSQL на комп'ютер користувача не виконувалася.
- Початкова Alembic-міграція для **нової PostgreSQL-БД**; автоматичного перенесення SQLite немає. Стару SQLite збережіть окремо.
- Unicode-сумісність, aliases, нестандартні адреси та date filters перевіряються інтеграційними тестами. Великий пошук — synthetic 100 000 записів; це не benchmark повного виробничого геопакета й не гарантія latency іншого сервера.
- `connection refused`: перевірте службу PostgreSQL, порт, firewall, `psql`.
- `password authentication failed`: роль, pgpass, URL encoding; не публікуйте URL із паролем.
- `permission denied ... btree_gist/schema`: перевірте роль-власника і права розширення.
- `DATABASE_URL обов’язковий`: правильний worktree/.env/PROJECT2_ENV_FILE; не додавайте SQLite fallback.
- `схема неповна`: зупиніть сервер, перевірте current/history і backup, виконайте явний upgrade. Не лікуйте stamp head без реальної схеми.
- Конфлікт period/revision/lock: оновіть дані; не вимикайте guards, не повторюйте POST автоматично.

## Оновлення життєвого циклу подій

Ревізія планування — `0002_event_completion` після замороженого 0001. Два адитивні поля PersonEvent, два CHECK та відсутні SERVICE-підтипи додаються тільки явним `alembic upgrade head`. Дати/тривалість існуючих подій зберігаються; майбутні завершення не підтверджуються автоматично. Startup не оновлює схему. Порядок backup/upgrade, сумісність старих даних і окремі команди — [EVENT_CONTROL.md](EVENT_CONTROL.md#міграція-postgresql). Reset не потрібний.

Ревізія виправлень — `0003_event_corrections`: метадані анулювання PersonEvent, append-only історія виправлень, FK/check та заборона фізичного DELETE/редагування анульованих записів. Окремий backup/upgrade, без reset і startup-міграцій — [EVENT_CORRECTIONS.md](EVENT_CORRECTIONS.md#міграція).

Попередня ревізія `0004_event_catalog`: без нових таблиць/полів, деактивує DAY_OFF для нових подій і додає відсутній кадровий VLK. Історичні події та наявні користувацькі реквізити VLK зберігаються. Явний backup/upgrade, без reset і startup-записів — [EVENT_VIEWS.md](EVENT_VIEWS.md).

## Head 0005: історія призначень

Після 0004 застосовується адитивна **0005_assignment_history**: метадані анулювання PersonAssignment, assignment_audit, append-only/restore guards та предикати `annulled_at IS NULL` для assignment EXCLUDE/period guards. Існуючі ID/дати/накази залишаються, старі записи неанульовані, фальшивого аудиту/авторів немає. Потрібен backup та явний `python -m alembic upgrade head` на перевіреній цільовій БД; startup не мігрує. Reset не потрібний. Downgrade відхилено через втрату аудиту. Автоматично project2_dev/project2_prod не змінювалися; перевірки використовують тільки випадкові схеми project2_ci. Подробиці — [STAFF_HISTORY.md](STAFF_HISTORY.md).


## Security 1.1

Персональна автентифікація обов’язкова без залежності від значення старого PROJECT2_AUTH_ENABLED. Рекомендоване явне значення — 1. Production за відсутньої змінної теж захищений; явний 0 або старий dev bypass=1 відхиляються конфігурацією. Ніяких автоматичних користувачів, reset чи міграцій цей етап не виконує. HTTPS залишається обов’язковим для LAN/зовнішніх адрес; PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1 дозволяє тільки прямий loopback з персональним паролем/CSRF. Повний опис та Windows-перевірка — [SECURITY.md](SECURITY.md).


## Security 1.2 — оновлення до 0006_account_management

Ревізія етапу Security 1.2 — `0006_account_management` після `0005_assignment_history`. Адитивна міграція розширює CHECK `users.role` значенням master, додає partial UNIQUE `one_master`, CHECK активного персонального Master, таблицю account_audit/FK/index/check та append-only/account-policy triggers. Старі користувачі, хеші, ID, ролі й сесії зберігаються. Жоден користувач не підвищується автоматично; минулий аудит не вигадується. Guards відхиляють зміну ID/логіна, видалення User, демоцію/вимкнення Master та втрату останнього активного персонального Admin. Advisory lock має спільний із сервісом ключ поточної схеми.

Після перевірки конфігурації цільової development БД, backup звичайним pg_dump і перевірки можливості відновлення виконайте вручну з кореня репозиторію:

```powershell
python -m alembic current
python -m alembic upgrade head
python -c "from app.database.db import engine; from app.database.schema_check import require_current_schema; require_current_schema(engine); print('Schema OK')"
```

Startup схему не мігрує; reset або metadata.create_all для оновлення PostgreSQL не потрібні. Ці команди не запускалися на project2_dev/project2_prod в межах реалізації. Випробування міграції/конкурентності виконуються тільки у випадкових ізольованих схемах project2_ci. Downgrade заборонений через втрату аудиту/захисту Master; повернення — перевірений backup в окремій БД. Подальше явне призначення вже наявного Admin як Master — [SECURITY.md](SECURITY.md#явне-призначення-наявного-admin-як-master), без створення нового облікового запису.

## Security 1.3 — підготовка до 0007_mfa_sessions

Робочі БД автоматично не мігруються. Після backup БД та перевірки відновлення підготуйте постійний MFA key ring у secret store/окремому `.env` і його незалежний backup, визначте точні WebAuthn RP ID/origins для всіх процесів. Нові залежності встановлюються з requirements.txt. Приклади config не містять робочих ключів.

Зупиніть сервери й виконайте вручну в конфігурації свідомо вибраної development БД:

```powershell
python -m alembic current
python -m alembic upgrade head
python -m app.services.mfa_keys --initialize
python -c "from app.database.db import engine; from app.database.schema_check import require_current_schema; require_current_schema(engine); print('Schema OK')"
```

Ревізія **0007_mfa_sessions**: п’ять нових MFA-таблиць, nullable метадані UserSession, UNIQUE публічного ID, FK/index/CHECK та розширення дозволених account_audit операцій. Старі User/ролі/паролі/аудит/сесії не видаляються; старі сесії з NULL підтвердженням MFA більше не авторизують. Існуючі Master/Admin налаштовують перший фактор після пароля; startup не блокує сам факт відсутності у них MFA, але перевіряє постійний ключ/marker/RP/config. Єдиний Master і мінімум окремого Admin зберігаються. Downgrade заборонений; повернення — backup в окремій БД з відповідним key ring. Reset не потрібний.

Ініціалізація ключа не створює ні фактора, ні користувача. Ротація з усіма старими ключами й новим current key: `python -m app.services.mfa_keys --rotate`, атомарно та після зупинки серверів/backup. Деталі та явна локальна процедура відновлення Master — [SECURITY.md](SECURITY.md). PostgreSQL-тести використовують тільки project2_ci та випадкові схеми; development/production не змінюються.

## Організаційна структура — 0008_organization

Організаційна ревізія — **0008_organization** після 0007; поточний head — **0010_organization_hierarchy**. Вісім нових таблиць дерева/оперативного підпорядкування/аудиту/покриття/квитанцій/перепризначення, nullable організаційні FK старих StaffStructure/Position, періоди й логічне анулювання Position та метадані анулювання StaffVersion. Старі люди, накази, призначення, User/MFA й аудит зберігаються; автоматичного зіставлення й минулих фіктивних подій немає.

Нова ревізія замінює активний UNIQUE номера посади й EXCLUDE періоду версій на предикати `annulled_at IS NULL`; відкладений EXCLUDE OrgCoverage дає одне джерело на unit/date. Заморожені SQL `organization_tree_guards.sql` та `organization_staff_guards.sql` перевіряють дерево на всіх періодах, життя підрозділів, належність посад, чинність призначень і незмінність історії/аудиту. Schema checker вимагає нові таблиці, колонки, guards, CHECK та активні предикати.

Організаційні й кадрові записи серіалізує одна schema-scoped advisory xact lock перед row locks; raw SQL guards беруть ту саму lock. Це запобігає гонці призначення зі зміною джерела, але обмежує паралельність записів у межах схеми. Читання штатки не блокується.

Перед ручним `python -m alembic upgrade 0008_organization` зупинити застосунок, перевірити цільову БД/оточення й зробити перевірений backup із цього документа. Автоматичного startup upgrade, create_all чи reset немає. Downgrade не видаляє організаційну історію: відновлення — у нову БД з backup. Після upgrade потрібне явне GUI-зіставлення старих структур і всіх їхніх посад. Подробиці й приклад — [ORGANIZATION.md](ORGANIZATION.md).

Перевірки виконуються лише в project2_ci зі випадковою схемою на тест. Новий `tests/postgresql/test_organization_staff.py` перевіряє upgrade 0007→0008 двічі зі старими записами, ефективний ротний знімок без дублювання, DB guards, конкурентне підтвердження/призначення та rollback. Development/production у цьому етапі не змінювалися.
