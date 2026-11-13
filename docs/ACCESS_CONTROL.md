# Security 1.4 — права доступу

## Уточнення форм і повторного MFA

`/admin/access` зберігає чернетку в живій сторінці під час повторної перевірки особи. Інтерактивна панель повторно використовує чинний password/MFA flow; після успіху жодного автоматичного запису прав немає. Потрібне повторне натискання підтвердження. Подробиці — [SECURITY.md](SECURITY.md).

У призначенні шаблону числові inputs замінені на пошук + select: назва шаблону й повний шлях підрозділу (наприклад, «1 батальйон / 2 рота / 3 взвод»). `access_choices.js` використовує лише вже дозволені `initial.templates` та `matrix.rows`; не запитує неавторизоване повне дерево. Context-only рядки без manageable-дій не стають вибором; шлях може включати вже дозволені сервером назви предків. Різні гілки з однаковими назвами розрізняються повним шляхом; value залишається незмінним числовим ID. Нові/перейменовані шаблони оновлюють список без reload. Призначення неактивного шаблону не отримує нових бізнес-правил: він явно позначений у виборі, серверна семантика збережена.

У всіх формах starts_at/ends_at (шаблони, персональні винятки, тимчасове виконання, делегування) видно ДД.ММ.РРРР та 24-годинний ГГ:ХХ. `profile_datetimes.js` повторно використовує ProfileDates для дати й залишає named ISO datetime-local у hidden input. Порожня необов’язкова пара дозволена, неповна/неправильна пара блокує відправлення. Подальше перетворення місцевого часу браузера на UTC у `fields()` не змінено; UTC timestamp/інтервали сервера та правила успадкування/ALLOW/DENY лишилися чинними. Читабельність нативного datetime-local більше не залежить від локалі браузера.


Організаційні рівні та нові види (0010) не є джерелом прав: штатний власник Загін/Батарея сам по собі не додає ALLOW. Визначення рівня other використовує чинне organization/edit, revision та OrgAudit; зміна батька зберігає окрему organization/reparent. Оперативне підпорядкування не успадковує права. Поточні MFA/CSRF/session/backup-політики Security 1.4–1.5 не змінено; деталі ієрархії — [ORGANIZATION.md](ORGANIZATION.md).


Реалізація у `feature/security`, поверх перевіреного етапу організаційної структури (`2faf17f`). ACL-ревізія — `0009_access_control`, батьківська — `0008_organization`; поточний head Security 1.6 — `0011_security_operations_audit`. Робочі БД автоматично не оновлюються. Вхід, TOTP/WebAuthn, резервні коди, персональні сесії, CSRF та предметні правила попередніх етапів повторно використані.

## Ролі та перехід

| Роль | Системні повноваження | Предметні дані |
| --- | --- | --- |
| Master | Безпека, системні акаунти, призначення Admin, матриці та джерела прав | Тільки явні чинні правила. Саме ім’я/роль Master не відкриває анкети чи файли. |
| Admin | Керування звичайними User, скидання їхніх паролів, матриці й джерела прав | Захищений повний доступ до предметних даних. Матриця його не обмежує. |
| User | Власна безпека та сесії; керування матрицями лише за явним делегуванням | За серверною матрицею; без правил предметних прав немає. |

Admin не змінює системні акаунти Master/Admin і не призначає нових Admin. Один Master та захист останнього персонального Admin залишаються на рівні сервісів і БД. Власні сесії можна завершувати незалежно від ролі. Для щоденної предметної роботи Master може використовувати окремий персональний Admin; чужі паролі/MFA не передаються.

Security 1.6 розширює [резервування](BACKUP_AND_RESTORE.md): Master/Admin читають стан і журнали та зі свіжою MFA запускають створення/перевірку. Ключі, дозвіл автоматизації й серверне відновлення — тільки Master. Excel/USB — окремий погоджений системний запуск Master/Admin зі свіжою MFA, з публікацією лише worker у перевірене захищене серверне сховище. Немає довільного destination, предметного JSON чи download через цей API; звичайні предметні grants Master не додаються. User/делегування не дають backup-повноважень. Немає видачі архіву/довільного decrypt/restore через API. Нова ACL-категорія не додана. Аудит трьома вкладками `/admin/audit` відсікає заборонені предметні значення перед фільтрами, сортуванням, кількостями та TXT; Master не отримує їх автоматично. Для ручних операцій резервування повторно використано чинний MFA modal, без автоматичного POST replay.

Міграція переводить `editor` і `viewer` до `user`, збільшує revision і записує **реальну поточну операцію переходу** з автором NULL у `AccessAudit`. Не генерує дозволів, не вигадує минулих авторів. Зберігає ID, паролі, фактори, сесії й журнали; чинна сесія одразу використовує нову роль. Старі ролі після upgrade заборонені CHECK. Персональні користувачі мають пройти той самий MFA, що й раніше; password-only та legacy dev flags не відкривають даних.

## Моделі й джерела

`User.person_id` — nullable FK на `Person`, UNIQUE для непорожніх значень. Анкета й акаунт незалежні. Вимкнений акаунт не отримує доступу; уповноважений адміністратор може перевірити й підготувати його матрицю до ввімкнення. Зміна зв’язку має причину, revision та аудит; штатних призначень не створює й не змінює.

| Таблиця | Призначення |
| --- | --- |
| `access_rules` | ALLOW/DENY; рівно одне джерело: користувач, шаблон, політика посади або тимчасовий набір. Область global/unit/position/person; relative лише для шаблонів/політик. |
| `access_templates` | Названі активні/неактивні шаблони з revision. |
| `access_template_assignments` | Кілька призначень шаблонів користувачу на підрозділ, зі строками й активністю. |
| `position_access_policies` | Явно затверджена політика конкретної керівної штатної позиції. |
| `temporary_access` | Фіксований набір на визначений підрозділ, посаду-джерело й обов’язковий строк; дострокове відкликання. |
| `access_delegations` | Межі керування чужими ручними правилами: підрозділ, категорії/дії, строк. Предметних прав самі по собі не надають. |
| `access_reviews` | Відкриті/завершені контрольні завдання Admin/Master; partial UNIQUE не допускає двох відкритих завдань на користувача. |
| `access_audit` | Append-only: автор, цільовий користувач, UTC, операція, before/after та причина. |

Усі нові джерела мають FK/перевірки строків. Правила відкликаються, а не фізично видаляються. PostgreSQL і тестова SQLite захищають аудит від UPDATE/DELETE, а історію джерел — від DELETE. Предметні моделі та бізнес-правила не замінені ACL-таблицями.

## Обчислення

`services/access.Access` — єдиний обчислювач. Чинні джерела об’єднуються; збіг DENY завжди переважає ALLOW. Відсутність правила означає відсутність дозволу, тому не заважає іншому джерелу. ALLOW edit надає read. DENY read забороняє і редагування; DENY edit сам по собі не забороняє окреме дозволене читання. Admin має захищений предметний доступ поза редагованою матрицею.

Правило unit поширюється за основним датованим деревом на довільну глибину. Тисячі успадкованих правил не записуються. Оперативне підпорядкування не враховується. Явні правила на unit/position/person зберігають власні ID після організаційних змін.

Доступ до особи за підрозділом/посадою визначається її **фактичним чинним** неанульованим призначенням та чинним джерелом штатки. Відсутні або старі призначення не відкривають розширених категорій. Історичний запит до таблиці не повертає старі медичні права. Для колишнього військовослужбовця з дозволеної області залишається тільки погоджений базовий перегляд: ПІБ, актуальне звання, поточна посада, один основний активний телефон і чинний компонент фото. Завантаження фото в проєкті ще не реалізоване, використовується існуюча заглушка. Явні персональні/глобальні DENY діють і тут.

Строки — UTC timestamp із часовим поясом на вході; початок включно, завершення не включно. Перевірка відбувається на кожному запиті, кешу прав між запитами немає. `Access(at=...)` використовується для керованого часу тестів; повне історичне відтворення колись відкликаних ACL не реалізоване, такі зміни збережені в аудиті.

## Категорії й спеціальні дії

Реєстр `app/access_catalog.py` надає клієнту українські назви та дії. Базові категорії: `basic`, `personal`, `service`, `documents`, `medical`, `family`, `events`, `history`, `organization`. У кожній є read/edit. Додатково:

- organization: `reorder`, `reparent`, `bind`, `import`;
- personal: `create` — початкове атомарне створення анкети, ПІБ, відмінків і звання;
- documents: `override` — ручний статус, разом із дозволом редагування документа.

Спеціальна дія не є загальним edit. Зміна назви, сортування, підпорядкування й прив’язка штатних посад перевіряються окремо. Переміщення до іншого батьківського підрозділу потребує reparent також на цільову область. Імпорт потребує import, читання джерела та прав на предметні зміни; нова офіційна версія — доступу до всієї області власника, оскільки замінює її джерело. Старий глобальний інтерфейс `/admin/staff` лишається Admin; scoped-операції доступні в `/admin/organization/staff`.

Реквізити та копії документа мають спільний documents-доступ. Для документа, зв’язаного з медичним записом, додатково потрібна відповідна medical-дія: загальний файловий URL не обходить медичну заборону. Історичний аудит потребує history і предметної категорії. Файлові типи/розміри/сховище та перевірка належності документа конкретній особі збережені.

## Базові права за посадою та завдання

Потрібні одночасно: User–Person, чинне офіційне призначення, явний `Position.managed_unit_id`, активна затверджена політика цієї позиції. За назвою «командир» нічого не вгадується. **До затвердження політика порожня**; медицина й edit не видаються автоматично. Правила політики обчислюються для підпорядкованого підрозділу одразу, очікування перевірки їх не блокує.

Призначення/переведення керівника, зміна керівного зв’язку або політики та зміна основного підпорядкування створюють транзакційне завдання перевірки. Поки вже є відкрите завдання, дубль не додається. Завершення — тільки явне рішення Admin/Master з причиною й revision, збережене в аудиті. Після нового кадрового факту може виникнути нове завдання. Ручні дозволи на інші роти при переведенні не переписуються й не відкликаються.

Політика прив’язана до реального ID позиції. У новій версії штатки нові позиції не отримують політики за текстовою схожістю; їх потрібно явно затвердити. Нові версії залишаються вакантними, автоматичного перенесення людей немає.

## Шаблони, тимчасове виконання, делегування

Шаблон можна створити, скопіювати незалежно, змінити, деактивувати. Централізоване редагування шаблону з призначеннями потребує окремого підтвердження. Призначення на підрозділ може бути постійним/тимчасовим, його можна вимкнути й знову ввімкнути.

Тимчасове виконання не змінює PersonAssignment: адміністратор отримує пропозицію затвердженої політики й прибирає зайві ALLOW. Усі чинні DENY політики зберігаються у фіксованому наборі. Зміна політики посади надалі не розширює набір і не пересуває його на інший підрозділ. Відкликаний набір не поновлюється; потрібне нове явне погодження.

Делегований User керує тільки ручними правилами інших User у дозволених областях/категоріях/діях. Не змінює себе, Master/Admin, шаблони, політики, зв’язки акаунтів і джерела; не делегує повноваження далі. У матриці бачить дозволені клітинки та контекстний шлях до них, без чужих джерел й аудиту. Строк делегування обмежує можливість керувати; строки створених ним предметних правил задаються окремо.

## HTTP, сервіси й транзакції

`application_access` перевіряє чинну сесію/MFA/CSRF → `security/access.enforce` визначає реальні ID категорій → Router → Service → Repository → SQLAlchemy. Невідомий новий предметний маршрут не надає User/Master доступу до оголошення політики. Actor із body ігнорується; principal/session передаються з перевіреної сесії через Session.info.

Списки людей, Person Picker, штатка, історія, журнал/контроль подій, facets та сортування отримують scoped-проєкції. Заборонені значення не передаються в HTML/JSON чи копіювання; недоступні SQL-поля маскуються до фільтрації/сортування. User бачить тільки дозволені блоки анкети, read-only API повертає прапорці доступних дій. Наявні пресети, копіювання, Міражі, revision і підписані snapshot повторно використані.

`access_context.actor_operation` зв’язує явного довіреного сервісного автора з операцією та не дозволяє підмінити вже перевіреного HTTP-автора. `access_writes` — додаткова перевірка змін предметних ORM-записів перед flush. Транзакції з ідентифікованим автором зберігають незмінний знімок дозволів і фактичної області **до** кадрової/організаційної зміни: проміжний стан переведення чи reparent не змінює рішення посеред атомарної операції. Після commit наступний запит обчислює права заново.

Низькорівневі DB-owner CLI/seed та міграції без application principal лишаються довіреними серверними операціями. Це не додаткові HTTP-входи й не спосіб передати довільного автора через body. Для інтерактивних нових сервісних операцій необхідний перевірений контекст або явний trusted actor.

Керування правами потребує свіжої MFA (наявний короткий строк повторної перевірки), причини та revision для змінюваних записів. Управління ACL серіалізується існуючим schema-scoped організаційним advisory lock; правила/джерела, контрольне завдання та аудит пишуться однією service-транзакцією. Помилка аудиту/перевірки відкочує всю зміну. Repository не commit/rollback. Чинні сесії 15 хв / 8 год та Origin/CSRF не послаблюються.

## Інтерфейс і маршрути

`/admin` → «Права доступу» → `/admin/access`. Уповноважений делегований User має пряме навігаційне посилання. Матриця: дерево підрозділів/позицій, пошук, розгортання гілок і категорій, read/edit/спеціальні дії, явні ALLOW/DENY/успадкування, частковий стан і вибір усіх дій області. Окремий глобальний рядок дозволяє явно керувати правилами для всіх областей, зокрема створенням нової ще не призначеної особи. Вибір батька не створює копій правил дітей. Після збереження ефективний стан перераховується сервером; перед збереженням бейджі відображають останній підтверджений стан.

Окремі секції: User–Person, персональні/строкові винятки, шаблони, політики посад, тимчасові набори, делегування, відкликання, контрольні завдання, пояснення причин доступу та останні 200 операцій аудиту (в БД зберігається повний журнал). Для нових зовнішніх форм User–Person/персональних винятків використовується реальний ID анкети; ПІБ не відкривається Master лише через налаштування прав.

API: `GET /admin/access/data`, `/overview`, `/explain`, `/proposal`, `/templates/{id}`; POST `/users/{id}/matrix|rule|link|template|temporary|delegate`, `/templates[/{id}]`, `/policies/{position_id}`, `/rules/{id}/revoke`, `/sources/{kind}/{id}`, `/reviews/{id}/resolve` — усі під `/admin/access`. `GET /account/access` повертає тільки власну мінімальну довідку, без структури чужих прав. Нового входу/системи ролей не створено.

## Застосування міграції

1. Обрати перевірену БД й конфігурацію, зробити та перевірити backup. Зберегти окремий backup MFA-ключів і файлового сховища. Переконатися, що чинний Master та окремий Admin можуть увійти з MFA.
2. Переглянути `python -m alembic current` / `python -m alembic heads`; очікується шлях 0008→0009. Запланувати, які ручні правила надати колишнім Editor/Viewer: автоматичних дозволів не буде.
3. За окремим рішенням адміністратора виконати `python -m alembic upgrade head`. Startup сам міграцій не запускає. `create_all` для оновлення PostgreSQL не використовується; reset не потрібний.
4. Увійти Master для системної безпеки або Admin для предметної роботи. На `/admin/access` явно налаштувати матриці/шаблони, зв’язки й політики, перевірити пояснення та контрольні завдання.

Downgrade з видаленням ACL-історії заборонений; відновлення backup перевіряється в окремій БД. Міграції цього завдання виконувалися лише у випадкових тестових схемах `project2_ci`. `project2_dev`/`project2_prod` не використовувалися.

## Перевірки та межі

Тести: `tests/test_access_control.py`, `tests/test_access_http.py`, `tests/postgresql/test_access_control.py`, `tests/browser/access_control.cjs`, повні регресійні набори. Старі предметні фікстури Editor/Viewer замінені на User з **явними тестовими** grants у `tests/access_helpers.py`; виробнича міграція не використовує цей адаптер. Негативні ACL-тести починають із User без прав.

Фактичні підсумки поточного запуску наведені в [CURRENT_STATE.md](CURRENT_STATE.md). Навантаження на великих реальних організаціях, інші браузери й бойова конфігурація не перевірялися. Обчислювач читає джерела/топологію пакетно на запит; міжпроцесного кешу немає. Окремої системи фото, ACL-керування багатьма матрицями одночасно та відновлення історичних прав із минулого аудиту не додано.


## Результати запусків

Baseline: Python 1161 passed / 98 PostgreSQL skipped. Повний Python: **1202 passed / 102 skipped**; повний PostgreSQL 17 на project2_ci — **102 passed**; Node — **57 passed**; повний Chromium — **203 PASS**. Після останніх обмежень джерел Master/вимкнених User повторено **72** цільові Python-тести; вони входять до загального набору. Всі ці завершені команди повернули exit 0. Подробиці — CURRENT_STATE.md. Два старі deprecation warnings залишилися.

Браузерний сервер `tests/browser/serve_column_visibility.py` реєструє власні synthetic fixture-маршрути тільки у тестовому процесі. Для них окрема явна test policy вимагає справжню MFA-cookie/CSRF та Master/Admin: це дає змогу очистити тільки disposable fixture після переходу синтетичного Admin у Master. Предметні маршрути продовжують викликати справжній application_access/ACL; у production test policy і fixture-маршрути не реєструються. Новий ACL-набір створює права через реальні API, без автоматичних grants.

## Змінені файли

Усього 107 створених або змінених файлів.

### Застосунок

- `app/access_catalog.py`
- `app/account_policy.py`
- `app/database/postgresql.py`
- `app/database/schema_check.py`
- `app/database/transactions.py`
- `app/main.py`
- `app/models/__init__.py`
- `app/models/access.py`
- `app/models/accounts.py`
- `app/repositories/access_repository.py`
- `app/repositories/position_table_repository.py`
- `app/routers/access_control.py`
- `app/routers/account_management.py`
- `app/routers/accounts.py`
- `app/routers/admin.py`
- `app/routers/contacts.py`
- `app/routers/organization.py`
- `app/routers/organization_staff.py`
- `app/routers/persons.py`
- `app/security/access.py`
- `app/security/access_writes.py`
- `app/security/admin.py`
- `app/security/application.py`
- `app/services/access.py`
- `app/services/access_context.py`
- `app/services/access_management.py`
- `app/services/access_reviews.py`
- `app/services/access_views.py`
- `app/services/account_management.py`
- `app/services/accounts.py`
- `app/services/dev_auth.py`
- `app/services/document_files.py`
- `app/services/documents.py`
- `app/services/event_views.py`
- `app/services/medical.py`
- `app/services/mfa.py`
- `app/services/organization.py`
- `app/services/organization_import.py`
- `app/services/organization_staff.py`
- `app/services/person_events.py`
- `app/services/person_picker.py`
- `app/services/person_read.py`
- `app/services/profile_records.py`
- `app/services/service_person_create.py`
- `app/services/service_person_positions.py`
- `app/services/staff_read.py`
- `app/services/staff_service.py`
- `app/static/css/access.css`
- `app/static/js/access_matrix.js`
- `app/static/js/access_profile.js`
- `app/static/js/document_ui.js`
- `app/static/js/medical.js`
- `app/static/js/person_events.js`
- `app/static/js/profile_records.js`
- `app/table_fields.py`
- `app/templates/admin/access.html`
- `app/templates/admin/index.html`
- `app/templates/admin/user_detail.html`
- `app/templates/components/app_navigation.html`
- `app/templates/person/components/access_overview.html`
- `app/templates/person_access.html`
- `app/templates/person_form.html`
- `app/templates/person_positions.html`
- `app/templates/staff_history.html`
- `app/templating.py`

### Міграція

- `migrations/sql/access_guards.sql`
- `migrations/sql/access_schema.sql`
- `migrations/versions/0009_access_control.py`

### Документація

- `docs/ACCESS_CONTROL.md`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/DOCUMENTS.md`
- `docs/MEDICAL_AND_AWARDS.md`
- `docs/ORGANIZATION.md`
- `docs/POSTGRESQL_SETUP.md`
- `docs/SECURITY.md`
- `docs/STAFF_HISTORY.md`
- `docs/TABLE_UI.md`

### Тести

- `tests/access_helpers.py`
- `tests/browser/access_control.cjs`
- `tests/browser/account_management.cjs`
- `tests/browser/column_visibility.cjs`
- `tests/browser/organization.cjs`
- `tests/browser/security.cjs`
- `tests/browser/security_mfa.cjs`
- `tests/browser/serve_column_visibility.py`
- `tests/postgresql/test_access_control.py`
- `tests/postgresql/test_account_management.py`
- `tests/postgresql/test_application_security.py`
- `tests/postgresql/test_assignment_history.py`
- `tests/postgresql/test_mfa.py`
- `tests/postgresql/test_organization_staff.py`
- `tests/postgresql/test_organization_tree.py`
- `tests/postgresql/test_postgresql.py`
- `tests/test_access_control.py`
- `tests/test_access_http.py`
- `tests/test_account_management.py`
- `tests/test_admin_organization.py`
- `tests/test_admin_organization_staff.py`
- `tests/test_application_security.py`
- `tests/test_assignment_history.py`
- `tests/test_documents.py`
- `tests/test_event_corrections.py`
- `tests/test_mfa.py`
- `tests/test_name_cases.py`
- `tests/test_organization.py`
- `tests/test_organization_import.py`
