# Підстави військової служби та довідник ТЦК та СП

## Джерела даних

`PersonServiceBasis` у `app/models/service_basis.py` — окрема таблиця `person_service_bases` з FK `person_id`. Вона не створює `PersonAssignment`, `PersonServiceHistory` або Міражів. Старий `PersonServiceHistory.service_type` залишається текстом історичного джерела; автоматичного перенесення чи визначення нової підстави за ним немає.

Вид — лише `mobilization` або `contract`; українські назви спільні в `app/service_basis.py`. `is_current` — явний вибір користувача, а не висновок із дат/посади/часу створення. Partial unique index `one_current_service_basis` допускає не більше одного поточного запису на людину. Збереження нової поточної підстави атомарно знімає прапорець попередньої, зберігаючи весь її зміст в історії. Можна редагувати історичні записи й знову явно зробити їх поточними; відсутність поточного запису також дозволена. Датований період чинності або його автоматична реконструкція тут не запроваджуються.

Поля мобілізації: nullable `mobilization_date`, текстові `region`, `settlement` (до 250), `document_tcc_name` (до 500) та необов’язковий `tcc_office_id`. Власне формулювання з документа зберігається незалежно від установи й географічного довідника.

Поля контракту: nullable `contract_signed_date`, `contract_start_date`, `enlistment_order_date`, номер наказу `enlistment_order_number` (до 100) і `contract_unit` (до 250). Дата підписання відокремлена від початку служби та наказу. Усі чотири нові дати — **точні Date або NULL**, без підставлення компонентів чи копіювання однієї дати в іншу. Сервер, ORM і SQLite exact-тригери відхиляють неповні/некалендарні значення. Зв’язки порядку між незалежними документальними датами не вигадуються. Поля іншого виду служби очищуються лише при явному збереженні вибраного виду.

`SystemTimestamps` додає чинні UTC `created_at/updated_at` і оптимістичний `revision`. Звичайні форми їх не редагують. `HistoryModel`, `PersonEvent`, кадрові періоди й політики раніше наявних неповних дат не змінено.

## Довідник і м’яке зіставлення

`TccOffice` / `tcc_offices` незалежний від `geo_units`: official_name, normalized_name, type, region, settlement, необов’язковий parent_tcc_id, is_active, UTC/revision. Додаткові normalized_region/normalized_settlement утворюють разом із normalized_name унікальність установи. Нормалізація — наявні NFC/casefold/згортання пробілів; оригінальний регістр відображення зберігається.

Типи: `regional` — обласний; `city` — міський; `district` — районний; `united_district` — об’єднаний районний; `department` — відділ. Сервіс перевіряє існування батьківського ID і забороняє цикли. Довідник спочатку порожній; засівання вигаданих установ немає.

`match_status` зберігає результат **на момент збереження персонального запису**:

- `unknown` — довідникового посилання немає, навіть якщо введено власну назву;
- `matched` — нормалізована назва документа збігається з довідниковою; зазначені область/населений пункт також збігаються;
- `mismatch` — вибрано установу, але назва відсутня/відрізняється або відрізняються заповнені текстові компоненти місця.

Розбіжність і відсутність збігу не блокують збереження. `document_verified` — окремий явний прапорець ручної перевірки. Оновлення/перейменування/деактивація довідника не змінює персональних текстів, прапорців, revision чи результату попередньої перевірки. У формі показується також поточна офіційна назва пов’язаної установи. Неактивна установа зберігається в раніше створеному зв’язку, але не пропонується в новому пошуку. Неіснуючий ID є помилкою посилання: можна прибрати його й зберегти текст без довідника.

## Шари, маршрути й UI

`routers/service_bases.py` → `services/service_bases.py` → `ServiceBasisRepository`; `routers/admin_tcc.py` → `services/tcc_directory.py` / `tcc_import.py` → `TccRepository`. Репозиторії в `repositories/service_basis_repository.py` виконують SQL без commit. Читання пов’язаних установ анкети — одним пакетним запитом.

Кожне збереження та підтверджений імпорт використовує `service_transaction(immediate=True)`: BEGIN IMMEDIATE, повторна перевірка revision/дублікатів, flush, один commit або повний rollback. Зміна поточного запису й попереднього прапорця — одна операція. Існуючий `StaffService.write_unit` не змінено.

Маршрути:

- POST `/persons/{person_id}/service-bases` та `/{key}` — створення й редагування з перевіркою власника/revision.
- GET `/tcc/suggestions?q=&region=&settlement=` — до 30 активних підказок із серверним Unicode-пошуком, максимум 250 символів у параметрі; GET `/tcc/locations` — текстові області/населені пункти активного довідника.
- GET `/admin/tcc` — пошук, сторінки по 100 записів; GET/POST `/admin/tcc/new`, `/{key}/edit` — редактор, включно з деактивацією.
- GET `/admin/tcc/template.xlsx`, POST `/admin/tcc/import/preview`, `/import/confirm` — шаблон і двоетапний імпорт.

Анкета має окрему вкладку `#service-bases` з блоком «Підстава проходження військової служби»: нова форма й редаговані історичні записи. `service_bases.js` показує поля тільки вибраного виду; приховані fieldset вимкнені. ТЦК підказує назву, але заміна вже введеного формулювання потребує підтвердження. Область і населений пункт можна вводити вручну. Чернетка не втрачається при серверній відмові завдяки чинному `personnel_forms.js`; після успіху оновлюється анкета з повідомленням. «Загальна інформація» отримує вид служби **тільки** з поточного `PersonServiceBasis` через `person_read.full_profile`.

Усі `/admin/tcc` захищено чинним `require_admin`, POST додатково `check_csrf`. Токен/захищена cookie, HTTPS-політика й явно ввімкнений localhost-only dev-режим залишаються тими самими, що для словників ПІБ; див. [NAME_CASES.md](NAME_CASES.md). Публічні TCC endpoint-и лише читають підказки, не змінюють довідник. Повної системи користувачів/ролей це завдання не додає.

## Excel-формат

Порожній файл: [templates/tcc_offices_empty.xlsx](templates/tcc_offices_empty.xlsx), той самий формат завантажується через GUI. Єдиний потрібний аркуш — `tcc_offices`; інші аркуші не імпортуються.

Рядок 1 — точні системні заголовки в такому порядку; рядок 2 — українські підписи й не є даними. Записи починаються з **рядка 3**, повністю порожні пропускаються. Повідомлення містять реальний номер Excel.

| Колонка | Значення |
| --- | --- |
| `id` | Порожньо для нового запису/зіставлення за назвою і місцем; наявний додатний ID — для контрольованого оновлення, зокрема перейменування. Неіснуючий явно заданий ID відхиляється. |
| `official_name` | Обов’язковий текст до 500 символів. |
| `type` | Один із п’яти системних ключів вище. |
| `region` | Необов’язковий текст до 250; довідник географії не потрібен. |
| `settlement` | Необов’язковий текст до 250. |
| `parent_tcc_id` | Необов’язковий ID установи, що **вже існує**; для нової ієрархії спочатку додайте батьківські установи окремим імпортом. |
| `is_active` | Явно `1` або `0`; оновлення з `0` деактивує установу після підтвердження. |

Без ID зіставлення відбувається за унікальною нормалізованою трійкою «назва, область, населений пункт». Для перейменування збереженого запису необхідний його ID; зміна текстового ключа без ID означає іншу установу. Дублікати трійки, повтори ID, кілька рядків на один запис, формули, сторонні заповнені колонки, неправильні типи/посилання/цикли заборонені. Ліміти: 5 МБ файлу, 50 МБ розпакованого вмісту, 10000 рядків даних.

Preview показує нові/оновлені/незмінені/пропущені/помилкові записи та значення. Критичні помилки блокують весь імпорт. Режим `add` не змінює наявних установ; `update` потребує окремого підтвердження оновлень. Підписаний preview прив’язаний до admin-сесії, TTL і ресурсу `tcc` (не можна підтвердити його як словник ПІБ); вміст перевіряється digest. `TccImport` зберігає ID виконаної операції/digest/mode, запобігаючи повторному підтвердженню. Ревізії й дублікати повторно перевіряються під блокуванням. Повторне завантаження того самого Excel дає незмінені записи; нових дублікатів немає. За будь-якої помилки всі установи й квитанція імпорту відкочуються.

## Безпечне оновлення SQLite

Зупиніть сервер та інші SQLite-клієнти. З кореня репозиторію, з активованим оточенням:

```sh
python -m app.database.migrate_service_bases --database data/database/project2.db
```

Передумова — актуальна попередня схема, включно з `migrate_service_history`. Міграція не запускається автоматично. Перевіряє файл, maintenance lease, цілісність/FK, попередні колонки й кадрові/exact-order тригери. Створює захищену SQLite backup-копію `*.before-service-bases-UTC-RANDOM.sqlite3`, потім у BEGIN IMMEDIATE лише додає три нові таблиці/індекси й два exact-service-basis тригери. Наявні таблиці, їхні записи та тригери не переписуються. Неповна стороння нова таблиця відхиляється; збій DDL має повний rollback, backup залишається. Повторний запуск актуальної міграції — no-op без нової backup-копії.

Раніше створені міграції виключають ці майбутні таблиці зі своїх попередніх контрактів. `schema_check` підказує нову команду; свіжий `init_db`/staging створює моделі через чинний registry. Засівання TCC чи автоматичного перенесення старого service_type немає. **Робочу БД під час реалізації не мігрували й не скидали.**

## Перевірки

Нові Python-тести — `tests/test_service_bases.py`, Node — `tests/js/service_bases.test.cjs`, Chromium — `tests/browser/service_bases.cjs` у чинному runner. Дані синтетичні; SQLite тимчасова або in-memory. Перевіряються види/поточність/історичне редагування, незалежні точні/відсутні дати, raw SQL guards, довідниковий збіг/власні назви, ручна перевірка, незмінність документів після оновлення, revision/власник, rollback, repeat/stale Excel preview, дублікати/батьківські цикли, auth/CSRF, backup/idempotency/DDL rollback/maintenance lease та відповідність Excel-шаблону. Фінальні числа перевірок наведені в [CURRENT_STATE.md](CURRENT_STATE.md).

Команди (Python-набір у підготовленому ізольованому робочому каталозі з доступом до шаблонів, оскільки db_test використовує відносний шлях `data/database/project2_test.db`):

```sh
PYTHONPATH=/workspace/project_2 /workspace/project_2/.venv/bin/python -m pytest /workspace/project_2/tests/ -q
```

З кореня репозиторію:

```sh
node --test tests/js/*.test.cjs
PYTHON=.venv/bin/python CHROMIUM_PATH=/usr/bin/chromium node tests/browser/column_visibility.cjs
```

Шляхи Python/Chromium залежать від середовища. Браузерний runner сам створює in-memory SQLite. Повний результат: 582 Python, 34 Node, 107 Chromium-сценаріїв пройшли; основна БД не використовувалася для запису.

## Файли цього етапу

Створено:

- `app/database/migrate_service_bases.py`
- `app/models/service_basis.py`
- `app/repositories/service_basis_repository.py`
- `app/routers/admin_tcc.py`
- `app/routers/service_bases.py`
- `app/services/service_bases.py`
- `app/services/tcc_directory.py`
- `app/services/tcc_import.py`
- `app/static/js/service_bases.js`
- `app/templates/admin/tcc.html`
- `app/templates/admin/tcc_form.html`
- `app/templates/admin/tcc_preview.html`
- `app/templates/person/components/service_bases.html`
- `docs/SERVICE_BASES.md`
- `docs/templates/tcc_offices_empty.xlsx`
- `tests/browser/service_bases.cjs`
- `tests/js/service_bases.test.cjs`
- `tests/test_service_bases.py`

Оновлено:

- `app/database/migrate_contacts.py`
- `app/database/migrate_geography.py`
- `app/database/migrate_name_cases.py`
- `app/database/migrate_service_history.py`
- `app/database/schema_check.py`
- `app/main.py`
- `app/models/__init__.py`
- `app/service_basis.py`
- `app/services/dictionary_previews.py`
- `app/services/person_read.py`
- `app/templates/admin/index.html`
- `app/templates/person/components/profile_overview.html`
- `app/templates/person_full_info.html`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/SERVICE_CHRONOLOGY.md`
- `tests/browser/column_visibility.cjs`
- `tests/test_contacts.py`
