# Безпека — Security 1.1 та 1.2

Поточний етап — Security 1.2 у `feature/security`, база — Security 1.1 (`abaed84`). Потрібна явна адитивна Alembic-міграція 0006; reset не потрібний. Нижче описано збережений базовий захист 1.1 та окремо нове керування користувачами 1.2.

## Виявлені прогалини та рішення

- Старі кадрові сторінки й API не мали загальної автентифікації. Тепер `FastAPI(dependencies=[Depends(application_access)])` захищає **кожен** предметний маршрут, включно з динамічно підключеними роутерами й прямими POST. Нові маршрути успадковують цю політику.
- `PROJECT2_AUTH_ENABLED` раніше відкривав застосунок без значення `1`. Тепер `open_access()` завжди False; відсутність змінної та `0` не відкривають даних. Немає HTTP-створення спільного службового адміністратора.
- `PROJECT2_DEV_AUTH_BYPASS`, `PROJECT2_DEV_ADMIN_OPEN`, спільний `project2_admin` / PROJECT2_ADMIN_TOKEN не авторизують запит. Історичних користувачів/сесій не видаляли.
- Старі форми й fetch-запити не передавали персональний CSRF. Усі серверні POST-форми отримують приховане поле; імпортовані Jinja-макроси успадковують контекст. Спільний `security_session.js` додає заголовок для same-origin fetch без власного токена. Явно вказаний неправильний токен не замінюється.
- Адміністративні операції, включно зі старими `/staff/import`, `/staff/structures`, `/staff/versions`, `/staff/positions`, тепер потребують персональної ролі admin.
- OpenAPI/Swagger/ReDoc теж захищені; приватні файлові відповіді зберігають наявні private/no-store/nosniff. Для інших предметних відповідей встановлюється no-store та Vary: Cookie.

## Центральний потік

`app/main.py` → `security/application.application_access` → `security/accounts.current_user` → чинні `services/accounts.authenticate` / AccountRepository → UserSession/User.

Сесія перевіряється за HttpOnly cookie `project2_user`: строк, існування та активність користувача. Перевірений користувач і CSRF кешуються тільки в `request.state` одного запиту. Модулі документів/медицини повторно використовують той самий current_user, без окремої системи входу. Серверне персональне авторство документів/подій/призначень збережено.

Наявні ролі застосовуються послідовно:

| Роль | Предметні GET | Предметні зміни | Адміністрування / `/auth/users` |
| --- | --- | --- | --- |
| viewer | Так, з чинними предметними перевірками | Ні | Ні |
| editor | Так | Так, з чинними предметними перевірками | Ні |
| admin | Так | Так | Так |
| master | Так | Так | Так, включно з правами Admin у всіх предметних сервісах |

`POST /auth/logout` та `POST /auth/password` дозволені кожному персонально авторизованому користувачу з правильним CSRF. Це не новий конструктор ролей або ACL за людьми/підрозділами.

Усі unsafe-методи потребують точного токена цієї сесії: `X-CSRF-Token` або поле `csrf` для urlencoded/multipart-форм. JSON не дозволяє передавати CSRF як довільне предметне поле. Origin/Sec-Fetch-Site перевіряються сервером. Чужий Origin, неправильний/відсутній CSRF, звичайний користувач на адміністративному URL — 403.

## Доступні без входу винятки

| Маршрут | Пояснення |
| --- | --- |
| `GET /auth/login` | Форма входу без персональних даних. Транспорт усе одно перевіряється. |
| `POST /auth/login` | Чинний JSON-вхід із перевіркою пароля/lockout/Origin. Без cookie; не надає доступу без валідних облікових даних. |
| `GET/HEAD /static/...` | Статичні CSS, JS та інші ресурси UI. Приватні документи зберігаються поза static і видаються тільки захищеним API. |

Інших публічних API, експорту, документів, словникового lookup або відкритої реєстрації немає. `/admin/login` — лише сумісний захищений перехід до персонального адміністрування; спільний токен не приймається. Невідомі URL/непідтримувані методи можуть повертати 404/405 без даних; нормалізація trailing slash може повертати перенаправлення, ціль залишається захищеною.

Анонімний API, JSON-схема й файлові маршрути отримують 401 незалежно від Accept, зокрема при text/html. Лише визначені HTML-сторінки з Accept: text/html — 303 до `/auth/login?return_to=...`. Повернення допускає лише локальний шлях, відхиляє зовнішні схеми/hosts, `//`, зворотні слеші, керувальні символи та їх кодування. Дефолт — `/persons`. Після закінчення сесії fetch отримує 401, показується повідомлення й посилання на повторний вхід; предметні чернетки не надсилаються без сесії. Після повторного входу спільний клієнт оновлює CSRF, після logout сесія видаляється з БД і cookie очищується.

## HTTPS і локальна розробка

HTTPS обов’язковий для LAN/зовнішніх адрес. Єдиний HTTP-виняток — `PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1`, **одночасно** прямий peer-loopback і Host localhost/127.0.0.1/::1, без proxy/forwarded-заголовків. Це дозвіл транспорту, не обхід пароля чи CSRF. `PROJECT2_ADMIN_ALLOW_HTTP` не послаблює цю перевірку. На HTTPS cookie Secure; завжди HttpOnly, SameSite=Strict, Path=/, строк 8 годин. Production без явно заданого AUTH_ENABLED теж захищений; явний 0 або старі dev bypass відхиляються його конфігурацією.

Windows PowerShell, після налаштування наявної development БД:

```powershell
$env:PROJECT2_AUTH_ENABLED = '1' # необов’язковий явний запис; без нього також потрібен вхід
$env:PROJECT2_AUTH_ALLOW_LOCAL_HTTP = '1'
python -m app.services.bootstrap_account --username first-admin --display-name "Адміністратор"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Якщо в БД залишилися **лише незмінені** технічні `project2-open-access` / `project2-dev-local`, до bootstrap можна явно додати `--allow-legacy-technical-accounts`. Створиться перший персональний admin; старі користувачі/сесії/аудит не змінюються. За наявності будь-якого персонального облікового запису цей виняток відхиляється. HTTP `/auth/users` цей CLI-параметр не приймає.

Bootstrap — **явна** команда тільки для першого адміністратора в обраній БД, пароль запитується приховано; якщо адміністратор уже є, використайте його. Не виконуйте bootstrap повторно як reset. Нових користувачів додає персональний admin через чинний `/auth/users`; нову GUI керування користувачами на етапі 1.1 не реалізовували.

Перевірка браузером:

1. У приватному вікні відкрийте `http://127.0.0.1:8000/persons` — має відкритися форма персонального входу без кадрових даних.
2. Увійдіть під наявним персональним користувачем — повернення на `/persons`; перевірте штатку, журнал, анкету та дозволене редагування.
3. Роль viewer читає, але не змінює; editor не відкриває `/admin`; admin відкриває адміністративні форми/Excel.
4. Натисніть «Вийти», повторіть прямий перехід/API/file URL — дані недоступні без нового входу.

## Тестова автентифікація та межі етапу

У production/development немає тестового перемикача. `tests/http_auth.py` — явний клієнт регресій, який потребує PROJECT2_ENV=testing та ізольованого DB dependency override; створює синтетичного користувача у тестовій БД і входить через справжній `/auth/login`. Це реальна cookie/CSRF-сесія, а не override захисної залежності. Браузерні фікстури також використовують персональні сесії; їхні службові маршрути існують лише в test server і захищені загальною залежністю. PostgreSQL-тести — тільки project2_ci, випадкова схема на тест.

Перевірка `tests/test_application_security.py` перелічує ефективні маршрути всіх включених FastAPI-роутерів, а не тільки верхній app.routes: анонімний запит до кожного відхиляється, усі unsafe-операції перевіряють CSRF. Окремо перевіряються авторизовані ролі, закінчення/відкликання сесії, відключення користувача, flags=0/відсутність/dev, HTTPS/loopback/proxy, URL повернення та приватні файли.

Security 1.1 — базова персональна автентифікація. **Повноцінні ACL, 2FA, Passkey, наступні підблоки безпеки, резервування та новий загальний аудит тут не реалізовані.** Наявні предметні сервіси, моделі й аудит збережені. Кадрові write-unit/revision/підписані snapshot та файлові обмеження залишаються обов’язковими після входу.


## Результати попереднього етапу Security 1.1

| Набір | Успішні | Пропущені | Невдалі |
| --- | ---: | ---: | ---: |
| Повний Python legacy/config | 962 | 55 PostgreSQL | 0 |
| Повний реальний PostgreSQL 17 (тільки project2_ci) | 55 | 0 | 0 |
| Node | 53 | 0 | 0 |
| Фінальний повний Chromium | 166 сценаріїв | 0 | 0 |

Baseline перед змінами: 848 Python passed / 54 PostgreSQL skipped. Додатково повторені 203 цільові Python та 10 Chromium geography; syntax/Jinja/git diff --check пройшли. Два попередні deprecation-попередження залежностей залишилися. Навантажувальні тести й інші браузери не запускалися. Схема/моделі не змінені, working DB не мігрувалася/не скидалася. На момент завершення реалізації commit/push/merge не виконувалися.

## Файли попереднього етапу Security 1.1

- `.env.example`
- `app/database/settings.py`
- `app/main.py`
- `app/repositories/account_repository.py`
- `app/routers/accounts.py`
- `app/routers/admin.py`
- `app/security/access_mode.py`
- `app/security/accounts.py`
- `app/security/admin.py`
- `app/security/application.py`
- `app/services/accounts.py`
- `app/services/bootstrap_account.py`
- `app/static/js/geography.js`
- `app/static/js/login.js`
- `app/static/js/security_session.js`
- `app/static/js/table_workspace.js`
- `app/templates/admin/dictionaries.html`
- `app/templates/admin/dictionary_form.html`
- `app/templates/admin/error.html`
- `app/templates/admin/import_preview.html`
- `app/templates/admin/index.html`
- `app/templates/admin/login.html`
- `app/templates/admin/staff.html`
- `app/templates/admin/tcc.html`
- `app/templates/admin/tcc_form.html`
- `app/templates/admin/tcc_preview.html`
- `app/templates/components/app_navigation.html`
- `app/templates/components/assignment_operations.html`
- `app/templates/components/column_visibility.html`
- `app/templates/components/journal_header.html`
- `app/templates/components/security_session.html`
- `app/templates/components/staff_import.html`
- `app/templates/event_journal.html`
- `app/templates/event_problems.html`
- `app/templates/login.html`
- `app/templates/person/components/contacts.html`
- `app/templates/person/components/geography.html`
- `app/templates/person/components/modal_windows.html`
- `app/templates/person/components/names_history.html`
- `app/templates/person/components/rank_history.html`
- `app/templates/person/components/service_bases.html`
- `app/templates/person/components/service_chronology.html`
- `app/templates/person_create.html`
- `app/templates/person_created.html`
- `app/templates/person_detail.html`
- `app/templates/person_form.html`
- `app/templates/person_full_info.html`
- `app/templates/person_name_cases.html`
- `app/templates/person_positions.html`
- `app/templates/persons.html`
- `app/templates/search_person.html`
- `app/templates/staff_error.html`
- `app/templates/staff_history.html`
- `app/templates/staff_import_preview.html`
- `app/templating.py`
- `config/development.env.example`
- `config/production.env.example`
- `config/testing.env.example`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/DOCUMENTS.md`
- `docs/MEDICAL_AND_AWARDS.md`
- `docs/NAME_CASES.md`
- `docs/POSTGRESQL_SETUP.md`
- `docs/SECURITY.md`
- `tests/browser/assignment_history.cjs`
- `tests/browser/column_visibility.cjs`
- `tests/browser/dev_auth.cjs`
- `tests/browser/documents.cjs`
- `tests/browser/history_forms.cjs`
- `tests/browser/injury_vlk.cjs`
- `tests/browser/medical.cjs`
- `tests/browser/name_cases.cjs`
- `tests/browser/open_access.cjs`
- `tests/browser/security.cjs`
- `tests/browser/serve_column_visibility.py`
- `tests/browser/service_bases.cjs`
- `tests/browser/staff.cjs`
- `tests/browser/vlk_workflow.cjs`
- `tests/http_auth.py`
- `tests/js/security_session.test.cjs`
- `tests/postgresql/test_application_security.py`
- `tests/postgresql/test_assignment_history.py`
- `tests/postgresql/test_person_events.py`
- `tests/postgresql/test_postgresql.py`
- `tests/test_admin_staff.py`
- `tests/test_application_security.py`
- `tests/test_assignment_history.py`
- `tests/test_contacts.py`
- `tests/test_date_system.py`
- `tests/test_dev_auth.py`
- `tests/test_event_corrections.py`
- `tests/test_event_lifecycle.py`
- `tests/test_event_views.py`
- `tests/test_geography.py`
- `tests/test_name_cases.py`
- `tests/test_open_access.py`
- `tests/test_partial_date_models.py`
- `tests/test_person_events.py`
- `tests/test_service_bases.py`
- `tests/test_service_chronology.py`
- `tests/test_service_transactions.py`
- `tests/test_staff_history.py`
- `tests/test_table_field_catalog.py`
- `tests/test_table_workspace.py`

## Security 1.2 — Master/Admin та керування користувачами

Реалізація продовжує `feature/security` від `abaed84`; гілка `testing` не змінюється. Повторно використано User/UserSession, scrypt, централізований доступ, HTTPS, Origin, CSRF та восьмигодинний строк сесії. Нових публічних API немає.

| Роль | Повноваження |
| --- | --- |
| `master` | Усі права Admin у предметних сервісах, документах, медичних модулях та GUI; керування іншими користувачами. |
| `admin` | Створення Admin/Editor/Viewer, редагування, ролі, блокування, скидання чужих паролів, відкликання сесій та аудит. Будь-яка зміна Master заборонена. |
| `editor` / `viewer` | Чинні предметні дозволи; обом доступна зміна власного пароля. |

Master не створюється через HTTP, не вимикається, не видаляється й не передає роль через GUI. Master змінює власний пароль тільки з перевіркою поточного. Звичайне адміністративне скидання власного пароля заборонене для всіх ролей. Логін та ID після створення незмінні; фізичне видалення користувачів відсутнє й заборонене тригером.

БД допускає максимум одного Master через partial UNIQUE `one_master`. Персональним вважається запис із чинним механізмом `scrypt$`; історичні `open-access-only$` / `dev-only$` не враховуються в мінімумі Admin та показуються в керуванні лише для читання. Ім’я чи логін не надають прав.

Після початкового призначення Master потрібен щонайменше один **окремий активний персональний Admin**. Master не входить до цього числа. Останнього Admin не можна вимкнути або понизити навіть самому Master. Початковий стан без Master не блокує запуск. Одноразове підвищення єдиного Admin може тимчасово залишити нуль Admin: `/admin/users` попереджає Master та дозволяє створити першого Admin, без прихованого автоматичного користувача. Після створення його вже захищає мінімум.

### Сторінки й API

- `/admin` → «Користувачі» → `/admin/users`: ID, пошук за ID/логіном/іменем, роль, статус, точний час створення UTC.
- `GET/POST /admin/users/new`: створення користувача. Чинний `POST /auth/users` також залишається захищеним способом створення.
- `GET/POST /admin/users/{id}`: перегляд, відображуване ім’я та базова роль; username не редагується. Запис потребує актуального `revision`, зміна ролі — підтвердження.
- `POST /admin/users/{id}/state`, `/reset-password`, `/revoke-sessions`: підтверджені операції з revision та необов’язковим коментарем до 2000 символів.
- `GET /admin/users/audit?user_id=ID&page=1`: журнал із порівнянням дозволених полів, автором і часом UTC, по 50 операцій на сторінку. Також доступний JSON через `Accept: application/json` для списку, картки й аудиту.
- `GET /account/password`, `POST /auth/password`: поточний пароль, новий та підтвердження; доступно кожному авторизованому користувачу, включно з Viewer.

Звичайний користувач не реєструється сам. Усі POST використовують ту саму cookie/CSRF/Origin-перевірку. GUI очікує JSON-відповідь через спільний session/fetch-компонент: при помилці зберігає несекретні поля, очищує введені паролі й показує причину. Поля пароля не повертаються в HTTP-відповіді.

Вимкнення адміністратора (`is_active=False`) зберігає роль, відкликає всі сесії та забороняє новий вхід. Увімкнення не відновлює старі cookie. Тимчасовий lockout після помилок входу показується окремо; `failed_attempts` / `locked_until` не стираються адміністративним блокуванням або зміною пароля. Новий пароль 12–128 символів, scrypt, має відрізнятися від старого. Власна зміна й адміністративне скидання відкликають **усі** сесії користувача, включно з поточною. Зміна ролі застосовується з наступного HTTP-запиту без очікування закінчення сесії.

### Явне призначення наявного Admin як Master

Спочатку застосуйте нову ревізію на свідомо вибраній БД після backup; автоматично це не виконується. Увійдіть чинним Admin, відкрийте `/admin/users` і знайдіть **ID** свого наявного запису `username=admin`, `display_name=master`. Ці тексти лише допомагають перевірити вибір, не доводять право на підвищення.

У PowerShell із кореня репозиторію та активованим venv, з конфігурацією потрібної development БД:

```powershell
$targetUserId = Read-Host 'ID наявного персонального Admin зі сторінки /admin/users'
python -m app.services.promote_master --user-id $targetUserId
```

CLI показує ID/логін/ім’я/роль/активність, перевіряє чинного персонального Admin, відсутність іншого Master і тимчасового блокування входу, потім запитує поточний пароль цього Admin без відображення та точне підтвердження `MASTER N`, де N — введений ID. Перед записом повторно перевіряє revision, пароль та інваріанти під блокуванням. ID, username, display_name, password_hash, час створення й усі пов’язані дані зберігаються; змінюються роль/revision/системний updated_at та додається аудит. Після успіху створіть окремого Admin через GUI. Повторне призначення й HTTP-призначення Master відхиляються.

Команда не запускалася для реальних користувачів. Відновлення втраченого пароля Master, перенесення власності та аварійна зміна Master не реалізовані на цьому етапі; це не прихований API обходу.

### Транзакції та захищений аудит

`Router → accounts / account_management → AccountRepository → SQLAlchemy`. Repository не виконує commit. `account_write` володіє однією `service_transaction(immediate=True)`: SQLite використовує BEGIN IMMEDIATE, PostgreSQL — advisory transaction lock, окремий для поточної схеми, та FOR UPDATE цільового User. Одне блокування також використовується входом і виходом, щоб відкликання сесій не пропустило паралельний вхід. БД-тригери використовують той самий ключ синхронізації й захищають мінімум Admin, незмінність ID/логіна та Master також від звичайного прямого SQL. Конкурентні зміни перевіряють revision. Це блокування тільки керування обліковими записами, не кадрових операцій.

`AccountAudit` / `account_audit` зберігає actor_user_id, user_id, точний occurred_at UTC, operation, before/after й reason. Операції: create, edit, role_change, block, unblock, password_reset, password_change, sessions_revoke, promote_master. Знімки містять лише ID/username/display_name/role/is_active/revision, ознаку зміни пароля й кількість відкликаних сесій. Паролі, хеші, токени сесій і CSRF не копіюються в аудит. Автор GUI береться з перевіреної сервером персональної сесії; body actor_id ігнорується. Початковий CLI bootstrap має actor=NULL; підвищення Master підтверджене паролем цільового Admin і записує його ID.

Кадрові дані й предметні журнали не змінені. Зміна User, відкликання сесій та запис AccountAudit атомарні: відмова аудиту відкочує все. Тригери відхиляють звичайні UPDATE/DELETE аудиту в PostgreSQL і тестовій SQLite. Власник БД із правами DDL залишається адміністративною межею захисту, як у чинному предметному аудиті.

### Міграція та межі етапу

Адитивна `0006_account_management` після `0005_assignment_history` розширює CHECK ролей, додає обмеження Master, account_audit та guards. Наявні користувачі/сесії не видаляються, автоматичного Master або вигаданого минулого аудиту немає. Перевірка схеми очікує новий head/таблицю/обмеження/тригери. Startup тільки перевіряє схему. Робочі development/production БД не мігрувалися; reset не потрібний. Downgrade із втратою аудиту заборонений; потрібне окреме перевірене відновлення backup.

Security 1.3 (15 хвилин неактивності), 2FA/TOTP/Passkey, ACL за підрозділами, делегування та універсальний аудит програми не реалізовано. Політика абсолютних восьми годин сесії не змінена.

### Ручна перевірка Security 1.2

1. На перевіреній development БД застосуйте міграцію після backup; увійдіть чинним Admin, відкрийте «Адміністрування → Користувачі». Анонімний/Editor/Viewer не повинен отримати доступ.
2. Виконайте явну CLI-процедуру для підтвердженого ID. За нульового числа окремих Admin перевірте попередження, створіть Admin і переконайтеся, що попередження зникло.
3. Створіть Editor та Viewer, змініть ім’я/роль із підтвердженням. У двох браузерних сесіях перевірте застосування нових прав на наступному запиті.
4. Вимкніть тестового користувача: всі його сесії мають припинити працювати. Увімкнення не відновлює старих сесій. Останнього Admin вимкнути чи понизити неможливо.
5. Увійдіть окремим Admin: картка Master лише для читання, зміна ролі/пароля/стану/сесій Master через API — 403.
6. Перевірте скидання чужого та зміну власного пароля: старі cookie відкликані, потрібен новий вхід. Помилка підтвердження не змінює пароль, очищує секретні поля та зберігає решту форми.
7. Перегляньте журнал користувача: окремі операції, реальні автори, старі/нові значення та точний UTC; немає паролів/токенів. Спроба повторного створення Master відхиляється.


### Файли реалізації Security 1.2

- `app/database/postgresql.py`
- `app/database/schema_check.py`
- `app/main.py`
- `app/models/__init__.py`
- `app/models/accounts.py`
- `app/repositories/account_repository.py`
- `app/security/admin.py`
- `app/security/application.py`
- `app/services/accounts.py`
- `app/static/js/document_ui.js`
- `app/templates/admin/index.html`
- `app/templates/components/app_navigation.html`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/POSTGRESQL_SETUP.md`
- `docs/SECURITY.md`
- `tests/browser/column_visibility.cjs`
- `tests/browser/serve_column_visibility.py`
- `app/account_policy.py`
- `app/routers/account_management.py`
- `app/services/account_management.py`
- `app/services/promote_master.py`
- `app/static/js/account_management.js`
- `app/templates/account_password.html`
- `app/templates/admin/account_audit.html`
- `app/templates/admin/user_detail.html`
- `app/templates/admin/user_new.html`
- `app/templates/admin/users.html`
- `migrations/versions/0006_account_management.py`
- `tests/browser/account_management.cjs`
- `tests/js/account_management.test.cjs`
- `tests/postgresql/test_account_management.py`
- `tests/test_account_management.py`

### Фактично виконані перевірки Security 1.2

Baseline до змін: 962 Python passed / 55 PostgreSQL skipped. Остаточні результати:

| Команда / набір | Успішні | Пропущені | Невдалі |
| --- | ---: | ---: | ---: |
| `python -m pytest tests/ -q` | 1016 | 65 PostgreSQL без окремого URL | 0 |
| `PROJECT2_TEST_DATABASE_URL=…/project2_ci python -m pytest tests/postgresql/ -q`, PostgreSQL 17 | 65 | 0 | 0 |
| `node --test tests/js/*.test.cjs` | 56 | 0 | 0 |
| Повний Chromium, `PYTHON=.venv/bin/python CHROMIUM_PATH=/usr/bin/chromium node tests/browser/column_visibility.cjs` | 184 сценарії | 0 | 0 |

Окремо пройшли 192 Python перевірки HTTP/керування, 10 PostgreSQL перевірок нового модуля, 8 цільових Chromium сценаріїв і фінальна перевірка CLI. Додані регресії успішно перевіряють права Master на коригування документів, перегляд вилучених копій та медичний запис; прострочені сесії не входять до активного лічильника, але теж видаляються при відкликанні всіх сесій. Перевірено міграцію 0005→0006 зі збереженням старого ID/пароля без вигаданого аудиту, два конкурентні підвищення, конкурентні блокування/пониження (також прямим SQL), rollback при помилці аудиту, revision, CSRF/Origin, авторство й відсутність секретів у відповідях/знімках. Перевірка схеми відхиляє індекс Master без унікальності.

Python/JS syntax, усі Jinja-шаблони, `alembic heads` (єдиний 0006), CLI `--help` та `git diff --check` пройшли. Два попередні deprecation-попередження FastAPI/Starlette залежностей залишилися; навантажувальні тести й інші браузери не запускалися. Тимчасовий PostgreSQL-контейнер зупинено після перевірок; випадкові CI-схеми видалені фікстурами. Робочі БД/користувачі, testing і HEAD не змінені; commit/push/merge/reset не виконувалися.
