# Єдина історія служби, накази, Міражі та текстовий пошук

## Джерела істини й модель

PersonAssignment залишається єдиним штатним призначенням. Штатка, /staff/history і повна анкета читають та змінюють його справжній ID через StaffService. Призначення ніколи не копіюється в PersonServiceHistory; третьої таблиці зведеної історії немає.

Додані поля:

- Person.personal_number — nullable String(100), один актуальний жетон, без унікальності та історії; обрізаються крайові пробіли, порожнє стає NULL, маски немає. Зміна — окремий особистий/обліковий блок у ПІБ; огляд читає поле напряму. Не виводиться в діагностичні логи.
- PersonAssignment.assignment_order_number/date, release_order_number/date — необов'язкові реквізити. Номери до 100 символів, дати — повні календарні Date або NULL. completion_reason (release/transfer/version_closed) та completion_note зберігають причину завершення, не створюючи вигаданого наказу.
- PersonServiceHistory отримав end_day/month/year, nullable проєкцію end_date, note та revision. Початок використовує наявні position_day/month/year, наказ — наявні order_*; ці дати допускають невідомі компоненти за явними DATE_FIELDS. Старі дати/UTC/is_active не змінюються.
- PersonPositionMirage — окремий неофіційний запис person_id/staff_position_id, status waiting/converted/cancelled, note/cancel_reason, UTC/revision та converted_assignment_id. Partial unique index one_waiting_mirage_per_person допускає максимум один waiting на людину; різних кандидатів на одній посаді може бути багато.

PersonEvent та системні UTC залишилися точними й не використовують нові неповні дати.

## Штатні операції

StaffService.write_unit з BEGIN IMMEDIATE, rollback, revision та чинними SQLite-тригерами збережено. create_assignment приймає необов'язковий наказ. Signed preview таблиці містить реквізити наказів (включно з необов'язковим наказом завершення попередньої посади при переведенні); POST assign читає їх лише з підписаного snapshot і повторно перевіряє source/target/version/position revisions. Зміна номера наказу збільшує revision й інвалідує попередні підтвердження.

correct_orders змінює тільки передані реквізити: відсутній ключ не очищує інші поля, порожнє явно передане значення очищує необов'язковий реквізит. Людина, посада та період не змінюються. correct_assignment залишається окремим шляхом виправлення дат/посади з усіма перевірками конфліктів; переведення фактичної служби виконується assign, який завершує A і створює B, не переписуючи A на B.

release_assignment вимагає revision, точну дату першого дня поза посадою й явне підтвердження. assigned_to = release_effective − 1 день, включна семантика збережена. Дата має бути після початку; операція не подовжує наявний період. Може скоротити первісне призначення, обмежене кінцем версії; вже завершене release/transfer/version_closed потребує окремого виправлення історії для іншого завершення. Без номера/дати наказу записується NULL. Повтор не створює нових призначень. Закриття версії ставить version_closed лише там, де обмежило призначення; не вигадує наказ і не означає звільнення зі служби.

Перенесення «Міражу» використовує той самий внутрішній _assign_locked під зовнішнім write_unit, не обходячи snapshot/конфлікти. Цей приватний метод не викликається напряму з HTTP.

## Незалежна історія та читання

service_chronology.chronology формує read-DTO з source_type/source_id, посадою/частиною, періодом, обома наказами, станом, діями та вихідним ORM-записом. Пара (source_type,source_id) не змішує однойменні числові ID різних таблиць. Сортування — за фактичними відомими компонентами початку, без використання created_at; невідомий рік не вигадується.

Незалежний редактор дозволяє текстову частину/посаду, часткові періоди, наказ і примітку. Новий запис не стає штатним чи автоматично актуальним; is_active — явний прапорець відомостей незалежної історії. Порожній запис без частини/посади заборонено. Редагування перевіряє owner/revision. Штатні записи не можуть потрапити сюди через маршрут редагування наказів. Після додавання [окремих підстав служби](SERVICE_BASES.md) поточний вид служби в огляді читається лише з PersonServiceBasis; старий service_type не переноситься й не використовується для автоматичного визначення нової підстави.

Подальша прив'язка історичного тексту до пізніше завантаженої штатки залишена окремим етапом: потрібні явний preview, підтвердження особи/посади, відновлення точних дат, snapshot конфліктів та атомарне створення/зіставлення через StaffService. При реалізації слід зберегти походження текстового запису й виключити подвійне відображення через явний зв'язок, а не схожість назв. Зараз автоматичного чи частково реалізованого зв'язування немає; namespace DTO та окремі вузькі операції готують цю межу. Тести підтверджують, що наявне читання/редагування не створює копій штатних записів.

## Міраж

waiting не приєднується як PersonAssignment і не впливає на офіційний статус/поточну посаду/зайнятість. Його можна створити на вакантній або зайнятій посаді, навіть коли кандидат офіційно займає іншу посаду. Статус не є датованим періодом: фільтр показує поточні waiting-закріплення вибраної версії, а не реконструйований стан Міражів на минулу дату.

Оформлення: окремий signed preview з mirage ID/revision та штатним snapshot → явне підтвердження → повторна перевірка → атомарне офіційне призначення й converted із посиланням на нього. Якщо ціль офіційно зайнята (включно із вже призначеним кандидатом), оформлення відхиляється: потрібне окреме завершення/скасування. Чужа посада не звільняється автоматично. Якщо кандидат має іншу посаду, текст підтвердження прямо повідомляє про завершення попереднім днем. Скасування вимагає причини, не створює призначення. Статуси/походження зберігаються.

У штатці офіційний рядок і приглушений «Міраж» розділені; без офіційного призначення напис «Вакантна» залишається. Незалежний URL-фільтр mirage=all/with/without не змішується з occupancy. Завантаження Міражів — один bulk-запит на результат, не N+1.

## Маршрути й UI

- POST /persons/{id}/personal-number — вузька зміна жетона.
- POST /persons/{id}/service-history та /{record_id} — незалежні записи.
- POST /personnel/assignments/{id}/orders, /release, /period — спільні штатні операції.
- POST /personnel/mirages — попереднє закріплення.
- POST /personnel/mirages/{id}/prepare, /convert, /cancel — signed оформлення й скасування.

Політика доступу кадрових сторінок незмінна. Новий спільний assignment_operations.html використовується в штатці, історії штату й анкеті. personnel_forms.js залишає чернетку/відкриту форму при помилці, показує причину; після успіху оновлює поточну сторінку з підтвердженням. service-history — стабільний hash вкладки, «Посада» збережена. Огляд читає жетон, поточний наказ/дату й окрему позначку waiting Міражу без summary-полів.

## Unicode «Містить текст»

Для кожного text-поля каталогу є whitelisted URL-ключ <column>__contains. Це окремий серверний фільтр, який можна поєднати з точними значеннями/іншими колонками/зайнятістю/версією/датою перегляду. Максимум один запит до 250 символів; порожній/пробільний не обмежує. «Пошук значень» у меню як і раніше тільки шукає серед опцій, а «Містить текст» запускає запит по всіх відповідних записах БД.

utils/text_search.py нормалізує NFC/casefold/пробіли. SQLite-функція unicode_contains реєструється на кожному SQLAlchemy connection разом з FK; SQLAlchemy передає введений текст як параметр. LIKE/LOWER не використовується для Unicode-підрядка, %, _ та SQL-подібні рядки не стають wildcard/SQL. Підхід — звичайний серверний scan, не FTS; на великих таблицях індексований пошуковий шар може бути окремим майбутнім етапом.

Додано необов'язкову computed-колонку full_address «Повна адреса реєстрації»: scalar-subquery чинної registration PersonAddress та чистий formatted_address UDF, ті ж текстові знімки й форматтер, без нової колонки/таблиці БД і без вимоги довідникового ID. За замовчуванням прихована; для пошуку через UI спочатку показати її. Каталог тепер має 55 інформаційних полів. Пошук за іншими майбутніми текстовими/computed-полями використовує той самий contains_clause.

QueryFilterAdapter.column_keys зіставляє contains-ключ з базовою колонкою: приховування знімає обидва режими тільки цієї колонки, Undo/Redo відновлює значення/order, сортування й поточний контекст зберігаються. Немає багаторівневого сортування або SQL з довільного клієнтського імені моделі.

## Міграція

Зупинити сервер і SQLite-клієнти. З кореня:

```sh
python -m app.database.migrate_service_history --database data/database/project2.db
```

Потрібна попередня актуальна схема, включно з контактами/географічним provenance. Maintenance lease, перевірка sidecars/попередньої схеми/цілісності/FK/кадрових тригерів, SQLite backup API (*.before-service-history-UTC-RANDOM.sqlite3, 0600), BEGIN IMMEDIATE, адитивні ALTER ADD та створення Міражу/індексів. Новий revision незалежних записів отримує 1; дати, жетони та накази не вигадуються. Існуючі тригери не видаляються й їхня семантика не змінюється; додаються два exact_assignment_orders тригери для повних необов'язкових Date. Помилка DDL відкочує транзакцію, backup залишається. Повторний запуск no-op. Старі міграції обмежені своєю попередньою схемою через service_schema.ADDED_COLUMNS, а не починають вимагати нові поля.

Автоматичної міграції/скидання БД немає. Новий init_db/reset використовує чинний model registry й створює нову схему/guards на staging без міграцій; робочий reset не запускався. Перевірка поточної схеми підказує окрему команду міграції.

## Результати перевірок за етапами

- Етап 1 (жетон/накази): 35 цільових тестів пройшли.
- Етап 2 (звільнення/переведення/вузькі зміни): 37 пройшли.
- Етап 3 (незалежні записи/DTO): 6 сервісних тестів пройшли.
- Етап 4 (Міражі/кадровий UI): 60 цільових тестів пройшли.
- Етап 5 (Unicode/каталог/комбінації): 49 цільових тестів і Node-набір пройшли.
- Фінально: повний Python-набір 537 passed; після уточнення read-only часової перевірки виду служби — 38 focused passed. Node 32 passed. Повний Chromium-прогін — 102 PASS-сценарії без pageerror, включно з 4 новими наскрізними personnel-сценаріями. Ці числа перекриваються й не підсумовуються.

Міграція перевірена на тимчасовій попередній SQLite: початкові призначення/дати/тригери збережені, backup створено, повтор no-op, штучна помилка після DDL відкочує всі додані поля/таблицю/guards. Перевірено rollback переведення при майбутньому конфлікті, stale snapshot/revision, multiple waiting-кандидатів без зайнятості, повні накази й заборону часткових order Date у raw SQL, Unicode-комбінації, ручну адресу без ID, буквальні SQL-подібні рядки та приховування contains через адаптер. Штатна книга/довідники й робоча БД не змінювалися; існуючі кадрові/датові/контактні/географічні тести пройшли.

Браузерні тести адаптовано до нових вкладених кадрових details і додано очікування завершення Bootstrap-backdrop перед drag. Виробничу логіку копіювання чи Drag & Drop не переписували; нові необов’язкові поля згорнуті, щоб не збільшувати рядки таблиці надмірно.

## Змінені файли

- `app/database/base.py`
- `app/database/migrate_contacts.py`
- `app/database/migrate_geography.py`
- `app/database/migrate_name_cases.py`
- `app/database/migrate_service_history.py`
- `app/database/schema_check.py`
- `app/database/service_schema.py`
- `app/date_fields.py`
- `app/main.py`
- `app/models/__init__.py`
- `app/models/mirage.py`
- `app/models/person.py`
- `app/models/person_military_service.py`
- `app/models/staff.py`
- `app/repositories/position_table_repository.py`
- `app/repositories/service_history_repository.py`
- `app/routers/person_positions.py`
- `app/routers/service_chronology.py`
- `app/routers/staff.py`
- `app/services/mirage.py`
- `app/services/person_read.py`
- `app/services/service_chronology.py`
- `app/services/service_person_positions.py`
- `app/services/staff_service.py`
- `app/static/js/personnel_forms.js`
- `app/static/js/table_filters.js`
- `app/table_fields.py`
- `app/templates/components/assignment_operations.html`
- `app/templates/person/components/profile_overview.html`
- `app/templates/person/components/service_chronology.html`
- `app/templates/person_full_info.html`
- `app/templates/person_positions.html`
- `app/templates/staff_history.html`
- `app/utils/text_search.py`
- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/SERVICE_CHRONOLOGY.md`
- `docs/TABLE_FIELDS.md`
- `tests/browser/catalog.cjs`
- `tests/browser/column_visibility.cjs`
- `tests/browser/history_forms.cjs`
- `tests/browser/layout.cjs`
- `tests/browser/personnel.cjs`
- `tests/browser/staff.cjs`
- `tests/js/text_filters.test.cjs`
- `tests/test_service_chronology.py`
- `tests/test_table_columns.py`
- `tests/test_table_field_catalog.py`
