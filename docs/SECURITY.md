# Security 1.1 — обов’язковий персональний вхід

Гілка реалізації — `feature/security`, база — `testing` / `00cf012`. Схема БД, User/UserSession, кадрові правила та предметний аудит не змінюються. Міграції й reset для цього етапу не потрібні.

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

`POST /auth/logout` дозволений кожному персонально авторизованому користувачу з правильним CSRF. Це не новий конструктор ролей або ACL за людьми/підрозділами.

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


## Результати фактичних перевірок

| Набір | Успішні | Пропущені | Невдалі |
| --- | ---: | ---: | ---: |
| Повний Python legacy/config | 962 | 55 PostgreSQL | 0 |
| Повний реальний PostgreSQL 17 (тільки project2_ci) | 55 | 0 | 0 |
| Node | 53 | 0 | 0 |
| Фінальний повний Chromium | 166 сценаріїв | 0 | 0 |

Baseline перед змінами: 848 Python passed / 54 PostgreSQL skipped. Додатково повторені 203 цільові Python та 10 Chromium geography; syntax/Jinja/git diff --check пройшли. Два попередні deprecation-попередження залежностей залишилися. Навантажувальні тести й інші браузери не запускалися. Схема/моделі не змінені, working DB не мігрувалася/не скидалася. На момент завершення реалізації commit/push/merge не виконувалися.

## Змінені та створені файли

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
