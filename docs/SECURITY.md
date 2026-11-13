# Безпека — Security 1.1–1.6

## UI Security 1.4: повторне підтвердження без втрати чернетки

П’ятихвилинна серверна політика не змінена: `mfa.fresh` діє до `mfa_verified_at + 5 хв`, на самій межі потрібне повторне підтвердження. Реальна криптографічна перевірка Passkey у тесті підтвердила доступ одразу й за мікросекунду до межі; о 5 хв — 403. Підстав для окремого скорочення строку Passkey в коді не знайдено. Password-only, ослаблення CSRF/Origin або збільшення строку не додано.

На `/admin/access` технічний код `MFA_REAUTH_REQUIRED` обробляється як UI-подія. Відкривається Bootstrap modal з чинною `/account/security?reauth=1` у same-origin iframe. Це лише компактне відображення наявної форми: пароль → `/account/security/reauth` → чинний pending flow `/auth/mfa?reauth=1` → TOTP/Passkey/резервний код → `/auth/mfa/finish`. Query-параметр не є дозволом: обидві сторінки зберігають наявні перевірки сесії/flow, CSRF і Origin; embedded-вигляд MFA дозволений лише для reauth-flow.

Після успішного finish iframe надсилає тільки константне повідомлення про завершення; батьківська сторінка перевіряє origin і source конкретного iframe. Повідомлення закриває modal і пропонує переглянути чернетку. Воно не надає прав і не замінює серверної перевірки. Форми, матриця changes і revision залишаються в тому самому DOM/пам’яті; паролі/коди/чернетки не копіюються у localStorage/sessionStorage. Критичний POST не відтворюється автоматично: користувач сам повторно підтверджує дію, сервер знову перевіряє MFA/ACL/revision. Скасування залишає чернетку й не виконує дію.

`security_session.js` зберігає попередню поведінку інших сторінок: лише оброблена ACL-сторінкою cancelable-подія замінює стандартне посилання на безпеку. Security 1.5 та його серверні операції не змінено. Повторна MFA оновлює лише чинний час перевірки, не абсолютні 8 годин і не інші сесії. Межі й результати цього UI-виправлення — [CURRENT_STATE.md](CURRENT_STATE.md).


Поточний етап — Security 1.6 у `feature/security`, початковий HEAD `a5a4a2e`, схема **0011_security_operations_audit** після `0010_organization_hierarchy`. Повна специфікація ACL — [ACCESS_CONTROL.md](ACCESS_CONTROL.md), резервування/Windows/USB/відновлення — [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md), фактичний звіт — [SECURITY16_REPORT.md](SECURITY16_REPORT.md). Нижче збережено історичні описи; їхні старі результати не є новим запуском.

Вхід/MFA/CSRF/15 хв–8 год залишаються чинними. Master керує системою, але не отримує предметних даних автоматично; Admin має захищений повний предметний доступ і керує звичайними User. User отримує доступ за серверними ALLOW/DENY з ручної матриці, шаблонів, чинної затвердженої керівної політики, персональних і фіксованих тимчасових правил. DENY переважає. Editor/Viewer мігрують до User зі збереженням паролів/MFA/сесій/історії та **без автоматичних предметних grants**.

`/admin/access` надає матрицю, зв’язок User–Person, шаблони, політики посад, тимчасове виконання, делегування, контрольні завдання, пояснення й append-only аудит. Критичні зміни потребують свіжої MFA. Admin не змінює системні Master/Admin; інваріанти Master/останнього Admin збережені. Повторно реалізованої автентифікації немає.

## Security 1.6 — резервування, відкритий аварійний архів і аудит

Master/Admin зі свіжою MFA створюють і перевіряють копії через підписану чергу; User відхиляється. Повні AES-256-GCM копії — щогодини, з окремим щоденним full. Після кожної — фактичний ізольований PostgreSQL drill саме цього ID, з окремими integrity/drill статусами. Worker тримає обидва locks увесь цикл, відновлює чергу після restart, дозволяє одну повторну спробу та повідомляє про остаточну помилку. Автоматичне видалення постійних копій вимкнено.

Відкритий аварійний архів о 18:00 Europe/Kyiv — три книги Excel та накопичувальні документи/фото. Він не містить password/MFA/session/token/key матеріалу. Експорт — погоджена захищена системна операція Master/Admin зі свіжою MFA, тільки через worker на приватний зашифрований серверний каталог або дозволений USB. Відповідь API містить лише підсумок, без значень/файлів; звичайний предметний доступ Master і його зведений аудит не розширено. Підписаний серверний дозвіл Master не стає анонімним HTTP-доступом; автоматичне виконання має NULL actor і власний журнал дозволу. Розклад наздоганяє останній пропущений запуск після power return без вигадування історичного snapshot.

USB discovery і копіювання виконує OS worker; HTTP читає лише свіжий підписаний список і приймає незмінний ID. Перевіряються allowlist GUID, диск/серійна ідентичність, USB, NTFS, unlocked/full/active BitLocker, DACL, readonly/offline та місце. Directory handles/no-reparse/exclusive temp/rename без заміни захищають файловий запис. Старі/вручну змінені Excel не перезаписуються. Реальні Windows/USB/Win32 сценарії потребують ручних випробувань за runbook; mock не є їх підтвердженням.

`/admin/audit` об’єднує три логічні журнали. Предметний ACL застосовується перед пошуком, підрахунком, сортом і TXT; Master без предметних прав не отримує значень. Нові login/login_failed/mfa_failed/logout записи AccountAudit не містять введених облікових даних. SubjectAudit заповнює прогалини нових ORM-операцій, без backfill; спеціальні документальні/медичні/кадрові/організаційні/ACL журнали повторно використано. BEFORE отримується під row lock, AFTER — з фактично записаного рядка, тому застарілий ORM-об’єкт не фальсифікує незмінені поля. Аудит і зміна атомарні, UPDATE/DELETE журналів блокуються.

Master-only ключі/відновлення зберігають серверний захищений сценарій Security 1.5: нова порожня ізольована БД, підписаний одноразовий plan, явне підтвердження, перевірки та staged files. Копійовані сесії/flows відкликаються тільки в цілі. Offline recovery потребує OS administrator і справжніх пароля+MFA Master у копії. Немає HTTP archive download, arbitrary decrypt, emergency token чи автоматичного cutover. Шифровані ключі й капсула конфігурації зберігаються окремо; RPO/RTO — вимірювані цілі, не заявлені гарантії.

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
| User | За чинними scoped-правилами | За чинними scoped-правилами | Лише явно делегована матриця інших User у своїх межах |
| Admin | Повний предметний доступ | Повний предметний доступ | Звичайні User та предметне адміністрування |
| Master | Лише явні предметні правила | Лише явні предметні правила | Системна безпека, системні акаунти та ACL |


`POST /auth/logout` та `POST /auth/password` дозволені кожному персонально авторизованому користувачу з правильним CSRF. Ці власні операції не залежать від предметної матриці.

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
3. User без правил не бачить предметних даних. Перевірте окремі read/edit та DENY; Admin відкриває предметні форми/Excel, Master без предметних правил не відкриває анкети й файли.
4. Натисніть «Вийти», повторіть прямий перехід/API/file URL — дані недоступні без нового входу.

## Тестова автентифікація та межі етапу

У production/development немає тестового перемикача. `tests/http_auth.py` — явний клієнт регресій, який потребує PROJECT2_ENV=testing та ізольованого DB dependency override; створює синтетичного користувача у тестовій БД і входить через справжній `/auth/login`. Це реальна cookie/CSRF-сесія, а не override захисної залежності. Браузерні фікстури також використовують персональні сесії; їхні службові маршрути існують лише в test server і захищені загальною залежністю. PostgreSQL-тести — тільки project2_ci, випадкова схема на тест.

Перевірка `tests/test_application_security.py` перелічує ефективні маршрути всіх включених FastAPI-роутерів, а не тільки верхній app.routes: анонімний запит до кожного відхиляється, усі unsafe-операції перевіряють CSRF. Окремо перевіряються авторизовані ролі, закінчення/відкликання сесії, відключення користувача, flags=0/відсутність/dev, HTTPS/loopback/proxy, URL повернення та приватні файли.

На етапі 1.1 було додано базову автентифікацію; MFA реалізовано в 1.3, scoped ACL — у 1.4 (див. актуальний опис на початку). Наявні предметні сервіси, моделі й аудит збережені. Кадрові write-unit/revision/підписані snapshot та файлові обмеження залишаються обов’язковими після входу.


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

На момент завершення 1.2 MFA й ACL ще не реалізовувалися. Актуальна реалізація MFA описана нижче, ACL/делегування — у ACCESS_CONTROL.md; універсального аудиту всіх дій програми немає.

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

## Security 1.3 — обов’язкова MFA та сесії 15 хв / 8 год

У `feature/security` поверх d44ee79 повторно використано User/UserSession, AccountAudit, scrypt, current_user, CSRF/Origin/HTTPS та account_write. Password-only доступу, винятку для Master/LAN, нових службових користувачів або відкритої реєстрації немає. Опис 1.1/1.2 вище — попередні етапи; поточний вхід завжди двоетапний.

### Двоетапний вхід і перехід

`POST /auth/login` перевіряє пароль/lockout і видає тільки `project2_pending`: HttpOnly/SameSite=strict cookie на 5 хвилин. `AuthFlow` у БД прив’язаний до user_id, відбитка чинного password_hash, конкретного випадкового cookie та CSRF. Усі операції flow перевіряють transport/Origin/строк/одноразовість/спроби. Проміжний стан не є UserSession і не відкриває предметних сторінок, файлів чи адміністративних API.

За відсутності фактора доступна тільки `/auth/mfa` для початкового налаштування. Користувач підтверджує TOTP або Passkey, отримує 10 резервних кодів і натискає завершення. Реєстрація першого фактора анулює інші незавершені спроби налаштування того самого користувача. За наявності MFA потрібен TOTP, Passkey або резервний код після пароля. Лише `POST /auth/mfa/finish` після перевірки фактора створює повну UserSession/cookie/CSRF й одноразово споживає flow. Зміна пароля або відкликання пов’язаної сесії робить flow недійсним.

Старі сесії залишаються в БД із NULL mfa_verified_at та відхиляються. Існуючі Master/Admin/Editor/Viewer проходять той самий початковий процес; ID, роль, пароль та історія зберігаються. Немає пільгового періоду без MFA, автоактивації чи автоматичної зміни робочої БД.

### Фактори та резервні коди

- TOTP: `pyotp` RFC 6238, випадковий 160-бітний base32 секрет, SHA-1 / 6 цифр / 30 секунд, вікно ±1 крок. Збережений last_step забороняє повторне використання й приймання старішого коду. Активація лише після правильного коду; QR генерується локально `qrcode`/наявним Pillow, секрет доступний для ручного введення. Секрет у БД — Fernet ciphertext із key ID, ніколи plaintext.
- Passkey: `webauthn` перевіряє реєстрацію/підпис assertion, challenge, RP ID, дозволений origin, presence, обов’язкову user verification, credential конкретного користувача й sign counter. Challenge у БД короткоживучий, одноразовий, також витрачається при невдалому підтвердженні. Сервер зберігає тільки credential ID/публічний ключ/лічильник/назву. Можна додати кілька ключів, перейменувати та відкликати. Видалення фактора відкликає всі сесії. Останній фактор видалити не можна — спочатку додається інший. Passwordless-входу немає.
- Резервні коди: 10 випадкових 96-бітних кодів, у БД тільки SHA-256 від високoентропійного значення. Показуються лише у відповіді генерації; GUI дозволяє копіювання/завантаження й не зберігає їх у localStorage. Використання одноразове, після правильного пароля; новий набір анулює попередній. У налаштуваннях видно лише залишок. Після резервного входу UI рекомендує зареєструвати новий фактор.

Невдалі MFA-спроби збільшують лічильник flow та чинний лічильник User: після п’яти — 5 хвилин блокування; правильний пароль самостійно цей лічильник не скидає. Crypto/input помилки не виводять вміст credential/кодів у повідомлення. Зміна фактора/кодів та AccountAudit атомарні, помилка аудиту відкочує зміну.

### Конфігурація, backup та ротація ключів

Обов’язкові налаштування з `.env` поза Git або спеціалізованого secret store:

- `PROJECT2_MFA_KEYS` — JSON key ID → Fernet key; кожний key — base64 від 32 випадкових байтів.
- `PROJECT2_MFA_CURRENT_KEY` — ID для нового шифрування; старі ID лишаються в ring до ротації всіх ciphertext.
- `PROJECT2_WEBAUTHN_RP_ID` — явно задане DNS-ім’я без схеми/порту; локально `localhost`.
- `PROJECT2_WEBAUTHN_ORIGINS` — JSON-масив точних origin зі схемою та портом. Локально, наприклад, `http://localhost:8001`; LAN/зовнішній доступ — HTTPS. RP ID та origins не беруться з довільного Host.

Генерація ключа виконується адміністратором один раз у захищеному середовищі: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Збережіть значення у secret store/окремому `.env`, не в Git, чаті, логах чи командному аргументі. Зробіть незалежну зашифровану резервну копію key ring; самої копії БД недостатньо. Усі процеси сервера повинні мати однакові стабільні налаштування. Втрата ключів робить чинні TOTP-секрети нерозшифровуваними.

Після backup БД та ручного `alembic upgrade head`, до запуску сервера: `python -m app.services.mfa_keys --initialize`. Це явний запис зашифрованого контрольного значення, не призначення фактора. Повторний initialize перевіряє наявний ключ. Startup тільки читає marker/схему/config і відмовляє за відсутності чи невідповідності key ring; випадковий ключ на кожний запуск не генерується.

Ротація: зупиніть серверні процеси; збережіть backup БД і старого key ring; додайте новий key ID, залиште старі, змініть current ID; виконайте `python -m app.services.mfa_keys --rotate`. Операція атомарно розшифровує старими ключами та повторно шифрує marker/TOTP/незавершені setup-секрети поточним ключем. Відсутній старий ключ відкочує все. Після перевірки ротації, нового backup і всіх процесів зі спільною конфігурацією можна прибрати невикористані старі ключі. Для відновлення старого backup БД потрібен відповідний старий ring.

### Сесії та повторне підтвердження

UserSession має окремі created_at, last_activity, expires_at, mfa_verified_at та випадковий публічний ID. На кожному захищеному запиті сервер перевіряє 15 хвилин від last_activity й максимум 8 годин від created_at/абсолютного expires_at. Повторна MFA оновлює тільки час підтвердження, не створення чи абсолютний строк. Одна сесія не продовжує інші. Відкликання 1.2 залишається негайним.

Звичайні GET/polling/refresh не змінюють last_activity. Спільний `security_session.js` реагує на trusted pointerdown/keydown, не частіше одного разу на хвилину надсилає `/account/activity` з cookie/CSRF. Оновлення серіалізоване, не відновлює вже прострочену сесію й не зсуває абсолютну межу. Локальний таймер показує попередження за 2 хвилини; сам таймер не надсилає heartbeat. Сервер не може криптографічно довести фізичну дію людини за звичайним HTTP-запитом: автентифікований клієнт може імітувати activity, але не перевищити абсолютні 8 годин. Погоджений GUI не підтримує сесію фоновим polling.

Свіже підтвердження — останні 5 хвилин. Воно потрібне для власного пароля, додавання/видалення/перейменування факторів, нових резервних кодів, MFA recovery та всіх операцій керування користувачами. Централізований guard повертає 403 `MFA_REAUTH_REQUIRED`; на сторінці безпеки користувач повторно вводить пароль і підтверджує MFA. Старої восьмигодинної сесії недостатньо.

### Сторінки й API 1.3

- `/auth/mfa`: обмежений другим етапом flow; `/state`, POST `/totp/start`, `/totp/confirm`, `/prove`, `/passkey/options`, `/passkey/verify`, `/finish`. Це вузький pre-auth контур, не анонімний предметний API; кожний маршрут вимагає чинного pending cookie, усі POST — його CSRF та Origin.
- `/account/security`: TOTP/Passkey, перейменування/відкликання, залишок та генерація резервних кодів, повторна перевірка особи. JSON `/state`; POST `/reauth`, `/add-factor`, `/backup`, `/remove`, `/rename`.
- `/account/sessions`: власні сесії; GET `/data`, POST `/revoke` для однієї іншої або всіх інших. Поточна завершується чинним logout. У відповідях тільки випадковий публічний ID та точний UTC; token_hash/token/CSRF інших сесій не видаються.
- `POST /account/activity`: продовження idle строку тільки чинної сесії.
- `POST /admin/users/{id}/reset-mfa`: чинний account-management handler, fresh MFA, підтвердження перевірки особи й обов’язкова причина. Картка користувача має форму операції.

### Відновлення

Після правильного пароля резервний код замінює другий фактор один раз. Якщо втрачені всі фактори/коди, Master/Admin з власною свіжою MFA документує перевірку особи й явно підтверджує reset-mfa іншого персонального користувача. Його фактори, flow, коди й сесії відкликаються атомарно з аудитом; наступний пароль відкриває тільки обов’язкове нове налаштування. Пароль/роль/ID не змінюються. Адміністративне скидання власного MFA та MFA Master через HTTP заборонене.

Для Master є тільки явна серверна команда з локальними правами Administrator/root: `python -m app.services.recover_master_mfa --user-id ID`. Вона перевіряє поточний пароль Master, вимагає документованого способу перевірки особи/причини та точного `RESET MFA MASTER ID`. Перед записом пароль перевіряється ще раз у транзакції. Audit має actor=NULL та пояснення локальної процедури, без фіктивної персональної сесії. Після скидання все одно потрібні правильний пароль та нове MFA; emergency token/прихованого HTTP endpoint немає. Процедура не відновлює забутий пароль Master і не замінює організаційну перевірку особи адміністратором ОС.

### Моделі, транзакції та аудит

Нові `TotpFactor`, `Passkey`, `RecoveryCode`, `AuthFlow`, `MfaKeyState` з FK/UNIQUE/CHECK та індексами. `routers/mfa.py → services/mfa.py → MfaRepository/AccountRepository → SQLAlchemy`. Налаштування crypto/RP — `security/mfa_config.py`; новий UI — `security_mfa.js`. Синхронізація — той самий account_write (PostgreSQL advisory xact lock поточної схеми, SQLite BEGIN IMMEDIATE), без локальної пам’яті для перевірки факторів/challenge. Metadata — поточна схема; `0007_mfa_sessions` містить заморожені визначення, не імпортує живі моделі.

AccountAudit отримав mfa_enroll/factor_add/factor_remove/backup_use/backup_generate/mfa_recover/mfa_reauth. Зберігаються реальний user_id/actor, вид/ID фактора, безпечні реквізити, причина й точний UTC. Паролі, TOTP/QR, приватні ключі, резервні коди, повні challenge та session tokens не копіюються в аудит. Існуючі append-only guards залишаються. Це розширення аудиту облікових записів, не новий загальний журнал програми.

### Локальна перевірка

Після підготовки конфігурації/міграції/key initialization відкрийте **http://localhost:8001** лише з явним `PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1`, або налаштований HTTPS origin. Введіть чинний пароль, додайте TOTP у Google/Microsoft Authenticator/Aegis через QR або вручну, підтвердьте код, збережіть резервні коди та завершіть вхід. Перевірте, що до завершення `/persons` недоступна. Для Passkey відкрийте «Безпека → Додати фактор» і виконайте системний діалог Windows Hello/Android/FIDO2; браузер мусить підтримувати WebAuthn та налаштований DNS origin. IP-адреса як RP ID не підтримується, перевірки origin/RP/UV не вимикаються.

У «Мої сесії» увійдіть з другого браузера, завершіть його сесію й перевірте негайний 401; власна сесія збережеться. Без дій 15 хвилин сервер відмовить навіть за активного polling; після 8 годин — незалежно від взаємодії. Для тестів часу використано керований clock, а не реальне очікування.


У разі втрати TOTP, але наявності резервного коду, можна увійти з паролем/кодом і в межах свіжого підтвердження вибрати «Додати фактор → Замінити TOTP». Старий секрет діє до підтвердження нового; підтвердження атомарно замінює його й завершує всі сесії/flow. Старі резервні коди не змінюються без явної генерації нового набору. Це дозволяє відновлення й у браузері без Passkey.


### Результати перевірок Security 1.3

Baseline до змін: 1016 Python passed / 65 PostgreSQL skipped. Фінальні фактичні запуски:

| Набір | Успішні | Пропущені | Невдалі |
| --- | ---: | ---: | ---: |
| `python -m pytest tests/ -q` | 1060 | 71 PostgreSQL без окремого URL | 0 |
| `PROJECT2_TEST_DATABASE_URL=…/project2_ci python -m pytest tests/postgresql/ -q`, PostgreSQL 17 | 71 | 0 | 0 |
| `node --test tests/js/*.test.cjs` | 57 | 0 | 0 |
| Повний Chromium `tests/browser/column_visibility.cjs` | 187 сценаріїв | 0 | 0 |

Після перенесення власних сесій/activity із роутера до сервісу повторно пройшли 34 цільові MFA-тести, включно з межею freshness під час налаштування фактора. Реальне криптографічне підтвердження WebAuthn перевірено підписаними EC/P-256 credential/assertion у Python та Chromium CTAP2 virtual authenticator з обов’язковим UV. Перевірені погані origin/RP/challenge/UV/signature, повторні challenge/TOTP/резервні коди, конкурентні спроби у PostgreSQL, старі сесії/Master після міграції, окремі процеси сервера, ротація ключа, freshness/idle/absolute з керованим clock, rollback аудиту та регресії 1.1/1.2/предметних модулів. Регресійні клієнти проходять справжній другий фактор через явно підготовлені синтетичні MFA-фікстури; application bypass не додано.

Не перевірялися фізичні Windows Hello/Android/USB-ключі, інші браузери, реальне очікування 15 хвилин/8 годин, Windows-права Administrator, навантаження та зовнішній HTTPS deployment. ОС-перевірку root і серверний recovery Master перевірено на синтетичних даних. Організаційне підтвердження особи оператором не автоматизоване. Відновлення забутого пароля Master не входить у цю процедуру. Два попередні deprecation-попередження FastAPI/Starlette залишилися.

Python/JS syntax, усі Jinja-шаблони, єдиний Alembic head 0007 та diff check перевірені. Старі ревізії 0001–0006 не змінені. Робочі БД/ключі/користувачі, testing та HEAD не змінені; commit/push/merge/reset не виконувалися. Наступні етапи Security 1.4 не реалізовувалися.


### Файли реалізації Security 1.3

65 змінених/нових файлів; тести попередніх модулів адаптовано до реального другого фактора.

- `.env.example`
- `app/account_policy.py`
- `app/database/maintenance.py`
- `app/database/postgresql.py`
- `app/main.py`
- `app/models/__init__.py`
- `app/models/accounts.py`
- `app/repositories/account_repository.py`
- `app/routers/account_management.py`
- `app/routers/accounts.py`
- `app/security/application.py`
- `app/services/account_management.py`
- `app/services/accounts.py`
- `app/static/js/medical.js`
- `app/static/js/security_session.js`
- `app/templates/admin/user_detail.html`
- `app/templates/components/app_navigation.html`
- `config/development.env.example`
- `config/production.env.example`
- `config/testing.env.example`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/POSTGRESQL_SETUP.md`
- `docs/SECURITY.md`
- `requirements.txt`
- `tests/browser/account_management.cjs`
- `tests/browser/column_visibility.cjs`
- `tests/browser/documents.cjs`
- `tests/browser/security.cjs`
- `tests/browser/serve_column_visibility.py`
- `tests/conftest.py`
- `tests/http_auth.py`
- `tests/js/security_session.test.cjs`
- `tests/postgresql/conftest.py`
- `tests/postgresql/test_account_management.py`
- `tests/postgresql/test_application_security.py`
- `tests/postgresql/test_assignment_history.py`
- `tests/test_account_management.py`
- `tests/test_application_security.py`
- `tests/test_assignment_history.py`
- `tests/test_document_ui.py`
- `tests/test_document_workflow.py`
- `tests/test_documents.py`
- `tests/test_event_corrections.py`
- `tests/test_medical.py`
- `tests/test_name_cases.py`
- `tests/test_profile_records.py`
- `app/models/mfa.py`
- `app/repositories/mfa_repository.py`
- `app/routers/mfa.py`
- `app/security/mfa_config.py`
- `app/services/mfa.py`
- `app/services/mfa_keys.py`
- `app/services/recover_master_mfa.py`
- `app/static/js/security_mfa.js`
- `app/templates/account_security.html`
- `app/templates/account_sessions.html`
- `app/templates/mfa.html`
- `migrations/versions/0007_mfa_sessions.py`
- `tests/browser/mfa_helpers.cjs`
- `tests/browser/security_mfa.cjs`
- `tests/js/session_activity.test.cjs`
- `tests/mfa_helpers.py`
- `tests/postgresql/test_mfa.py`
- `tests/test_mfa.py`
