# Система точних і неповних дат

## Поточна схема

Штатні версії та PersonAssignment тепер мають окремі **точні** Date-періоди; до неповних дат вони не належать. Поточність визначається фактичними датами, не created_at. Схема й нові команди засівання — [STAFF_HISTORY.md](STAFF_HISTORY.md).

На етапі розробки погоджено зміну SQLAlchemy-моделей без Alembic і без перенесення старих тестових даних. Реалізовано 15 nullable Integer-компонентів у трьох таблицях. Жодний наявний локальний або хмарний файл SQLite автоматично не пересоздавався.

| Модель | Джерело значення | Сумісні SQL Date-проєкції |
| --- | --- | --- |
| `Person` | `birth_day`, `birth_month`, `birth_year` | Немає, як і раніше |
| `Passport` | `passport_issued_day/month/year`, `passport_expire_day/month/year` | `passport_issued_date`, `passport_expire_date` |
| `PersonRank` | `rank_order_day`, `rank_order_month`, `rank_order_year` | `rank_order_date` |
| `PersonServiceHistory` | `position_day/month/year`, `order_day/month/year` | `position_date`, `order_date` |
| `PersonEvent` | Чинні Date: обов'язковий `date_start`, необов'язкові `date_end`, `order_date` | Усі задані значення точні; модель не змінена |
| `HistoryModel` | Чинні автоматичні DateTime: `created_at`, `updated_at` | Завжди точні системні часові позначки; модель не змінена |

Для п'яти нових предметних дат незалежно невідомі компоненти зберігаються як NULL. Проєкція Date містить точну дату лише за наявності всіх компонентів, інакше NULL. Відсутні частини ніколи не замінюються першим числом, січнем, поточним роком тощо.

## Обробка дат і сумісність

`app/date_fields.py` явно дозволяє неповноту для народження, дат паспорта, наказу про звання та історії служби. Рік народження обмежений поточним роком, інші перелічені предметні дати — календарем Python 1–9999. Події та системні DateTime не отримують частковості.

`PartialDateMixin` у `app/models/partial_date_mixin.py` використовується лише `Passport`, `PersonRank`, `PersonServiceHistory`. Він перевіряє компоненти чинним валідатором і синхронізує SQL Date-проєкції під час ORM insert/update. Публічні властивості зі старими назвами повертають точну дату або None; присвоєння їм повної дати розкладає її на компоненти, присвоєння None очищає їх. Приватні mapped-атрибути `_..._date` — лише проєкції. Прямі SQL/bulk-записи обходять ORM-перевірку: штатні зміни дат слід проводити через компоненти й наявні сервіси.

`record.date_components(prefix)` повертає перевірені компоненти, `Model.date_binding(prefix)` — явний binding для універсальних possible-match фільтрів і сортування. Для неповних дат не слід використовувати `DateBinding.exact` над Date-проєкцією: це втратить відомі компоненти неповного значення. Цей адаптер залишається для справжніх точних Date, наприклад `PersonEvent.date_start`.

`date_values_from_input` у `app/utils/date_utils.py` читає три компоненти, зберігає не передані частини під час сервісного редагування й підтримує старий точний `*_date` ввід. Змішування двох форматів відхиляється. Явні порожні компоненти означають NULL. `ServicePersonRankFunc` уточнює дату на існуючому записі, без створення нової історії лише через її уточнення. `CommonPersonFunc.add_pasport` приймає як старі точні аргументи, так і нові компоненти.

Додавання й редагування звання використовують спільний `date_input.html` / `date_input.js`; для кількох модальних форм передається унікальний `id_prefix`, назви полів лишаються стабільними. Сервер повертає 400 для некоректних дат. Відображення скрізь використовує `format_partial_date`: наприклад `_.03.1995`, `15._._`, `_._._`. Нового CRUD паспортів або історії служби цей етап не додає.

У `/person-positions` доступні шість предметних дат: `birth_date`, `rank_order_date`, `passport_issued_date`, `passport_expire_date`, `service_position_date`, `service_order_date`; всі, крім народження, типово приховані. Джерела та вибір історичних записів описані у [TABLE_FIELDS.md](TABLE_FIELDS.md). Кожна має свій JSON-фільтр, `<column-key>_priority` та ключ `project2:date-priority:<table-id>:<column-key>`. Фільтри поєднуються з чинним каскадом, приховування вилучає лише фільтр своєї колонки, undo/redo відновлює його. Відсутній вибраний запис людини/звання/паспорта/служби не вважається записом із невідомою датою. У таблиці повна відсутність компонентів показується як `-`; чинний форматтер для часткових значень і решти сторінок не змінено. Пресети продовжують зберігати тільки видимість/порядок, без сортування, ширин і дат.

## Системний час

`HistoryModel` використовує `datetime.now(UTC)` для default та onupdate. Тип DateTime не має `timezone=True`; SQLite серіалізує ці значення без timezone і повертає naive datetime. Чинна домовленість — ці значення означають UTC. Типи, спосіб зберігання й автоматичне оновлення не змінені. Відображення показує точну дату й час із позначкою UTC; звичайні форми не приймають системних часових позначок.

Майбутній Audit Log повинен мати точні часові позначки, користувача, таблицю, ID запису, поля та старі/нові значення. Зараз він не реалізований.

## Створення та повторне засівання

Команди виконуються з кореня репозиторію у Python-середовищі зі встановленими `requirements.txt`. Спершу можна створити окремий новий файл:

```sh
python -m app.database.init_db --database data/database/date_system_check.sqlite3
python -m app.seeds.seed_structure --database data/database/date_system_check.sqlite3
python -m app.services.seed_test_people --database data/database/date_system_check.sqlite3
```

`init_db` CLI відмовляється змінювати вже наявний файл без `--recreate`. `--recreate` вимагає явного `--database`, перевіряє SQLite-заголовок і відмовляється видаляти файл за наявності `-wal`, `-shm` або `-journal`. `create_all` не оновлює старих таблиць. Команди засівання перед записом виконують read-only перевірку поточної схеми (`app/database/schema_check.py`); автоматичних ALTER або reset немає.

Для ручного пересоздання **основної** SQLite спочатку зупинити вебсервер та всі підключення до неї. Перша команда нижче видаляє вибрану стару SQLite разом із її даними:

```sh
python -m app.database.init_db --database data/database/project2.db --recreate
python -m app.seeds.seed_structure --database data/database/project2.db
python -m app.services.seed_test_people --database data/database/project2.db
```

Ці команди перевірено на нових тимчасових файлах; проти основної БД вони не виконувалися. Старі `reset.py` / `reset_test_db.py` для цієї перевірки не запускалися. Якщо збереження старих даних знову знадобиться, потрібне окреме перенесення до компонентів, а не виклик create_all поверх старої схеми.

Без параметрів версії команда довідників більше не імпортує посади: після підготовки БД використайте UI імпорту з фактичними датами або CLI з --version-name та --valid-from/--valid-to. Засівання людей залишається окремим від довідників. Обидві seed-команди підтримують `--excel`; типовий файл — кореневий `reference_data.xlsx`. Аркуш `persons` не містить дат наказу про звання, тому всі три компоненти наказу в нових рядках залишаються NULL. Повторний імпорт не очищає вже внесені компоненти існуючих людей/звань.

На новій тимчасовій SQLite з актуальним Excel двічі отримано однакові кількості:

| Таблиця | Після першого запуску | Після повторного |
| --- | --- | --- |
| Типи / підтипи подій | 7 / 15 | 7 / 15 |
| Звання / посади | 21 / 10 | 21 / 10 |
| Люди / ПІБ / історія звань | 15 / 15 / 15 | 15 / 15 / 15 |

Перший імпорт знайшов і створив 15 людей, повторний знайшов 15 і пропустив усіх 15; помилок і дублікатів немає.

## Основні файли

| Ділянка | Файли |
| --- | --- |
| Політики, валідація, SQL | `app/date_fields.py`, `app/utils/date_utils.py`, `app/utils/date_query.py` |
| Моделі | `app/models/partial_date_mixin.py`, `app/models/person_identity.py`, `app/models/person_military_service.py` |
| Сервіси й обробники | `app/services/service_person_rank.py`, `app/services/service_common_person_func.py`, `app/routers/person_rank.py`, `app/routers/persons.py` |
| Таблиця посад | `app/table_columns.py`, `app/services/service_person_positions.py`, `app/routers/person_positions.py`, `app/templates/person_positions.html` |
| Введення й відображення | `app/templates/components/date_input.html`, `app/static/js/date_input.js`, `app/templates/person/components/modal_windows.html`, `app/templates/person/components/rank_history.html`, `app/templates/person_full_info.html`, `app/templates/person_detail.html` |
| Меню дати | `app/templates/components/date_filter.html`, `app/static/js/date_filter.js`, `app/static/css/date_fields.css` |
| Схема та засівання | `app/database/init_db.py`, `app/database/schema_check.py`, `app/seeds/seed_structure.py`, `app/services/seed_test_people.py` |
| Нові перевірки етапу | `tests/test_partial_date_models.py`, `tests/test_database_commands.py`, `tests/browser/domain_dates.cjs`; доповнено чинні тести дат, засівання та колонок |

Результати повного набору тестів та відомі обмеження — у [CURRENT_STATE.md](CURRENT_STATE.md).
