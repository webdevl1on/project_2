# Документи: інфраструктурний етап

Реалізовано моделі, загальносистемні персональні облікові записи/сесії, захищений JSON API, приватне файлове сховище, аудит і явну міграцію. Повний редактор вкладки «Документи», GUI входу/керування користувачами й вбудований переглядач копій **ще не реалізовано**; поточна вкладка залишається заглушкою. API вже доступний після явної міграції та створення персонального адміністратора.

## Незалежні поняття та моделі

`models/documents.py` містить погоджені сім моделей:

| Сутність | Джерело істини |
| --- | --- |
| DocumentType | Тип, назва, основний/додатковий, активність, ключ довіреної серверної схеми. |
| PersonDocumentState | Unique(person_id, document_type_id); фізична наявність PRESENT / NEVER_OBTAINED / UNKNOWN. Відсутній запис означає UNKNOWN. |
| PersonDocument | Конкретний запис, актуальність, заміна через replaces_id, FK на наявний Passport, ручне коригування та revision. |
| DocumentDetails | Реквізити інших документів: серія/номер/орган/вид, компоненти дат видачі/закінчення, режим строку, дозволені додаткові поля. |
| DrivingCategory | Категорія, власні компоненти дат початку/закінчення; окремо від строку посвідчення. |
| DocumentFile | Кілька front/back/page/other копій одного запису; UUID-подібний випадковий ключ, MIME, ім’я, розмір, SHA256, logical removal/revision. |
| DocumentAudit | Append-only операції, person/type/document/file, actor_id, точний UTC час, зміни old/new та причина. |

Поточний номер РНОКПП **лише** `Person.tax_number`; паспортні реквізити **лише** чинний `Passport`. PersonDocument посилається на Passport через unique nullable passport_id: таблиця Passport і її дати не змінені. DocumentDetails для passport/tax_number заборонено сервісом і SQLite-тригерами. Поточний РНОКПП не редагується через новий документальний API; на архівуванні історичний знімок фіксується тільки в журналі, звідки читається архівний номер. Це не друге редаговане джерело номера.

На особу допускається багато історичних документів типу та максимум один поточний — partial unique index. Явна заміна архівує попередній запис і створює новий в одній транзакції; реквізити й файли попереднього не переносяться і не видаляються. Історичні реквізити також можна виправити з аудитом. Звичайного фізичного видалення документів немає.

Фізична наявність не визначається з факту створення запису, реквізитів або копій. Явна зміна presence не змінює їх автоматично. NEVER_OBTAINED дозволено тільки додатковим типам; основні типи захищені також CHECK/SQLite-тригерами. Наявні записи/копії не знищуються навіть при такій позначці — це окреме твердження користувача. Для нього needs_requisites/needs_copies повертають false. Архівні записи також не входять до поточних потреб комплектування.

## Схеми, заповненість і строки

`app/document_schemas.py` — джерело типів, обов’язкових реквізитів та явних DateField-політик. Новий тип може використовувати наявну схему через schema_key; нова структура реквізитів потребує серверної схеми/валідації, але не перепроєктування lifecycle/files/audit. Клієнт не задає SQL чи довільні поля JSON.

Початкові типи: passport, tax_number, military, birth_certificate, driving_license, combatant, marriage_certificate, other. При створенні нової DocumentType таблиці додається лише цей довідник типів, без персональних документів/користувачів. Схеми:

- паспорт — тип, номер, видача, орган; книжечка додатково серія, ID додатково строк;
- РНОКПП — чинний номер із десяти цифр;
- військово-обліковий — вид, номер, видача;
- народження/УБД/шлюб — серія, номер, видача, орган;
- посвідчення водія — серія, номер, видача, щонайменше одна категорія;
- інший — номер.

Номер/серія зберігаються рядками. Відсутні реквізити дозволяють зберегти чернетку; некоректні введені значення відхиляються. Додатковий JSON наразі дозволяє лише note до 1000 символів; невідомі ключі відхиляються. Схема не вважає саму оболонку чи файл заповненим реквізитом.

Автоматично обчислюються NOT_FILLED / PARTIALLY_FILLED / FILLED. Файли й presence не входять у цей розрахунок. API повертає automatic_status, effective_status, override_status/reason/stale і has_copies окремо. Фільтр status використовує effective_status; automatic_status доступний незалежно. needs_requisites враховує чинне ручне коригування, але needs_copies не зникає від ручного FILLED.

Ручне коригування — тільки admin, з обов’язковою причиною й revision; воно не змінює реквізитів і не створює файлів. Скасування також потребує причини. Зміна реквізитів через сервіс очищує коригування з аудитом. Fingerprint вмісту виявляє зовнішню зміну canonical Passport/Person: тоді override_stale=true, старе коригування видно, але effective_status знову автоматичний. Читання не переписує БД й не вигадує автора зовнішньої зміни.

Існуючі неповні паспортні дати та спільні DateField/validate_field_date збережені. Дати нових реквізитів/категорій зараз точні або повністю порожні за явними політиками; компоненти не підставляються. Нові ORM-моделі також перевіряють календар. HistoryModel, PersonEvent, кадрові дати та UTC-політика не змінені.

Строк: UNKNOWN, INCOMPLETE, UNLIMITED, VALID, EXPIRING, EXPIRED. Неповна паспортна дата дає INCOMPLETE без вигаданого дня; категорії мають окремі попередження. `PROJECT2_DOCUMENT_EXPIRY_DAYS` — 0–3660, типово 30. Строк документа й початку/закінчення категорії перевіряються окремо.

## Загальносистемний доступ

`models/accounts.py`, repositories/account_repository.py, services/accounts.py, security/accounts.py та routers/accounts.py не залежать від модуля документів. User містить username, display_name, scrypt password_hash із випадковою сіллю, роль admin/editor/viewer, активність, UTC/revision. UserSession зберігає тільки SHA256 bearer-cookie, CSRF-токен і точний строк завершення.

Персональна HttpOnly/SameSite=Strict cookie має path=/, TTL 8 годин і Secure для HTTPS. Logout відкликає сесію в БД, прострочена/неактивного користувача не приймається. Права повторно перевіряються перед записом. Після п’яти невдалих спроб відомий обліковий запис блокується на 5 хвилин. Пароль — 12–128 символів; bootstrap читає його getpass, не з аргументів чи коду.

Ролі наразі загальносистемні: viewer читає документи/доступні копії, editor також записує/архівує/прикріплює, admin додатково створює користувачів, коригує статус і читає вилучені копії через явний history=true. Поособових ACL поки немає. Автор береться тільки з перевіреної сесії, actor_id з payload не приймається як автор. Журнал містить чутливі реквізити й теж потребує персонального входу.

`PROJECT2_DEV_ADMIN_OPEN` **не** відкриває новий API. Старі /admin словники/ТЦК залишаються на чинній окремій політиці. Для нового входу потрібен HTTPS; тільки прямий localhost/loopback може явно дозволити HTTP через `PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1`. Цей прапорець не прибирає пароль чи CSRF, не працює для LAN/forwarded-запитів. Кожен write після входу потребує X-CSRF-Token, а cross-site Origin/Sec-Fetch-Site відхиляється. Login приймає тільки JSON.

GET /auth/me повертає користувача та CSRF поточної сесії з no-store; POST /auth/login, /auth/logout, /auth/users — вхід, вихід і захищене створення користувача адміністратором. Відкритої реєстрації немає. GUI входу/адміністрування користувачів, відновлення пароля й загальний захист усіх старих кадрових сторінок — наступні етапи; ця зміна не переписує їхні поточні контракти. Персональний аудит нового модуля не є аудитом старих неавторизованих маршрутів редагування Person.tax_number.

## Сервіси, API та транзакції

Router → services/documents.py / document_files.py → DocumentRepository → SQLAlchemy. Репозиторії не commit/rollback. document_transaction використовує чинний service_transaction(immediate=True): повторна перевірка прав/revision, BEGIN IMMEDIATE, один commit для зміни й аудиту або rollback. SQLAlchemy-помилки запису перетворюються на загальне повідомлення без реквізитів у тексті SQL-помилки.

Базовий URL `/persons/{person_id}/documents`:

- GET — записи/віртуальні незаповнені позиції; фільтри code, status, automatic_status, presence, copies, current, expiry, needs_requisites, needs_copies;
- POST — type, details, необов’язкові replaces_id/revision для явної заміни;
- POST /{id} — редагування із revision;
- POST /presence — type, presence, revision наявного стану;
- POST /{id}/override — revision, status (або null), reason;
- POST /{id}/archive — revision;
- GET /audit — точний час, реальний actor_id або чесний actor_kind=migration, операція, old/new/причина;
- POST /{id}/files — multipart file, revision документа, side;
- GET /files/{file_id} — захищене завантаження, history=true лише для admin;
- POST /files/{file_id}/remove — revision файла, reason.

Усі ці маршрути потребують персонального входу, включно з читанням. Повідомлення про помилку JSON не спричиняє навігації; майбутній GUI повинен зберігати свою чернетку. Старі URL таблиці/фільтрів/пресетів/копіювання/Undo та кадрові сервіси не змінені.

## Файлове сховище

`DocumentStorage` — окремий адаптер з локальною реалізацією. Типово data/private_documents (виключено з Git), перевизначення `PROJECT2_DOCUMENT_STORAGE`. Каталог не може бути в app/static; випадкові 64-hex ключі не використовують ім’я користувацького файла. Нові каталог/файли створюються з 0700/0600 на POSIX. Шлях і symlink перевіряються.

До 10 МБ на копію; перевіряються сигнатури PDF/JPEG/PNG, а не тільки розширення. Це **не** повна перевірка структури файла/антивірус. Видача зараз attachment із private/no-store, nosniff та sandbox CSP; вбудованого preview немає.

Спочатку приватний тимчасовий файл, потім публікація під випадковим ключем перед commit метаданих/аудиту. При звичайній відмові SQL, аудиту чи публікації виконується компенсаційне очищення. БД і файлова система не мають спільної транзакції: аварійне завершення процесу може залишити тимчасовий/осиротілий файл; автоматичне очищення після crash і фізичний purge ще не реалізовані. При відсутньому файлі БД/журнал зберігаються, API повідомляє помилку. Вилучення зараз логічне, файл залишається для історії; архівування документа не змінює його копії. Backup експлуатаційної системи повинен включати і SQLite, і приватне сховище.

## Явне оновлення БД

Робочу БД під час реалізації не відкривали для міграції, не скидали й не засівали. Зупиніть сервер/SQLite-клієнти, активуйте середовище й з кореня виконайте:

```sh
python -m app.database.migrate_documents --database data/database/project2.db
```

Потрібна попередня актуальна схема включно з migrate_service_bases. Maintenance lease, integrity/FK та перевірки попередніх тригерів виконуються до запису; backup *.before-documents-UTC-RANDOM.sqlite3 створюється з 0600 SQLite backup API. BEGIN IMMEDIATE додає тільки нові таблиці/індекси/документальні guards; Persona/Passport/кадрові таблиці та існуючі тригери не переписуються. Створюється довідник типів, оболонки всіх паспортів і непорожнього РНОКПП; source-поля не дублюються. Presence залишається UNKNOWN через відсутність явного твердження. Не створюються користувачі, паролі, файли, ручні коригування або вигадані дати.

Якщо є кілька активних паспортів, міграція залишає їхні старі прапорці без змін, не обирає поточний у новому модулі й додає ambiguous_current до migration-аудиту. Це потребує явного подальшого розбору. Події міграції позначені actor_kind=migration без вигаданого персонального автора. Неповна стороння схема відхиляється; збій DDL/перенесення має rollback зі збереженням backup. Повтор актуальної міграції — no-op, без дублікатів оболонок/журналу/backup.

Для нової БД чинний init_db/model registry створює всі таблиці й базові типи. Старі міграції виключають майбутні таблиці документів/користувачів зі своїх попередніх контрактів. `schema_check` підказує окрему команду; startup не виконує міграції.

Перший персональний адміністратор створюється окремо, лише за відсутності користувачів:

```sh
python -m app.services.bootstrap_account --database data/database/project2.db --username admin --display-name "Адміністратор"
```

Пароль буде запитано двічі без відображення. Наступні користувачі — через захищений /auth/users. Створення першого адміністратора ніколи не виконується автоматично.

## Перевірки

`tests/test_documents.py` використовує tmp_path SQLite, синтетичні реквізити й тимчасове сховище. Перевіряє незалежність трьох станів, заборону NEVER_OBTAINED основним на сервісі/SQL, ролі/CSRF/сесії/lockout, override/reason/automatic/stale, canonical Passport/Person, exact/partial expiry, категорії, immutable audit, заміну/rollback, кілька копій/owner/історичний доступ, відмови диска/аудиту, backup/idempotency/DDL rollback та незмінність старих записів/тригерів.

`tests/browser/documents.cjs` — 3 наскрізні сценарії реального браузерного fetch: персональний вхід/CSRF, захищена копія незалежно від наявності/комплектності, override з реальним автором і втрата доступу після logout. Test-only setup існує тільки в tests/browser сервері, не реєструється production entry point. Файли браузерних тестів створюються в окремому tmp-каталозі й очищуються.

Команди: ізольований pytest tests/ (див. CURRENT_STATE), `node --test tests/js/*.test.cjs`, `PYTHON=.venv/bin/python CHROMIUM_PATH=/usr/bin/chromium node tests/browser/column_visibility.cjs`; тільки новий browser-набір — COLUMN_STAGE=documents. Результати — [CURRENT_STATE.md](CURRENT_STATE.md).

## Файли інфраструктурного етапу

Створено:

- `app/database/migrate_documents.py`
- `app/document_schemas.py`
- `app/models/accounts.py`
- `app/models/documents.py`
- `app/repositories/account_repository.py`
- `app/repositories/document_repository.py`
- `app/routers/accounts.py`
- `app/routers/documents.py`
- `app/security/accounts.py`
- `app/services/accounts.py`
- `app/services/bootstrap_account.py`
- `app/services/document_files.py`
- `app/services/document_storage.py`
- `app/services/documents.py`
- `docs/DOCUMENTS.md`
- `tests/browser/documents.cjs`
- `tests/test_documents.py`

Оновлено:

- `.gitignore`
- `app/database/migrate_contacts.py`
- `app/database/migrate_geography.py`
- `app/database/migrate_name_cases.py`
- `app/database/migrate_service_bases.py`
- `app/database/migrate_service_history.py`
- `app/database/schema_check.py`
- `app/main.py`
- `app/models/__init__.py`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `tests/browser/column_visibility.cjs`
- `tests/browser/serve_column_visibility.py`
