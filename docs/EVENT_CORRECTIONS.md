# Журнал: сортування, порядок колонок і виправлення

Доповнення до [EVENT_CONTROL.md](EVENT_CONTROL.md), без зміни правил планування, повернення, медичних завдань і штатних призначень.

## Сортування та представлення

Один серверний sort: name, unit, position_number, position_short або `date:YYYY-MM-DD:YYYY-MM-DD`. Заголовки перемикають ASC/DESC, `aria-sort` позначає активний напрямок. Для номера посади порядок числовий; порожні штатні значення завжди внизу. Текст нормалізується чинним Unicode-механізмом, однакові значення мають стабільний порядок за ПІБ/ID.

Календар сортує за розрахованим станом/підтипом за день, а для інтервалу — за назвою агрегованого стану та розподілом кількості днів. Денна проєкція й формула підсумків не змінені. Абсолютний інтервал сортування зберігається в URL під час зміни місяця/фільтрів/масштабу; підпис пояснює цей інтервал, навіть якщо він уже поза видимим періодом. Сортування не змінює дати чи події БД.

№ рахується заново за відфільтрованим і відсортованим переліком. Підсумок праворуч має скорочене ПІБ вибраної людини й точний видимий інтервал над категоріями. Без вибраної людини заголовок пропонує її обрати.

`journal_controls.js` адаптує чинні ColumnModel і ColumnInteractions: стабільні data-column-key, переставляння тих самих DOM-комірок, візуальне місце вставлення й блокування кліку сортування після drag. № системна й завжди перша в порядку, її видимість лишається опціональною, як у попередньому завданні. Решта колонок, включно з календарними, переставляються. Початкові дати хронологічні. Ключ календаря містить реальний початок/кінець інтервалу, а не позиційний індекс.

Порядок додається в чинний `project2:event-journal:layout:v1`; старі налаштування без order продовжують працювати. Width ПІБ, видимість додаткових колонок і прокрутка збережені. Нові дати, яких немає у збереженому порядку, додаються хронологічно. Закріплені заголовки/ПІБ збережені й після drag. CSV тепер використовує видимі колонки в їхньому поточному порядку та повні значення, з попередніми BOM/екрануванням/захистом формул.

## Виправлення типу

Зміна типу/підтипу використовує чинні редактор, edit endpoint і PersonEventService. UI показує підтвердження з попереднім/новим типом. «Скасувати» закриває тільки підтвердження, зберігаючи всі поля редактора. Зміна типу скидає несумісний підтип; сервер повторно перевіряє його належність, активність, дати та конфлікти.

Сервер і core-сервіс вимагають `confirm_type_change=True` (HTTP: `1`/`true`) саме при зміні event_type_id. Без цього прямий POST відхиляється. Зміна тільки підтипу не потребує окремого підтвердження типу. event_id зберігається; наявний expected_state захищає від застарілої форми.

У тій самій транзакції додається PersonEventCorrection: event_id, точний occurred_at UTC, actor_id NULL або реальний FK, operation=type_change та JSON before/after. Знімки містять усі реквізити події та назви типу/підтипу на момент зміни. Це історія погоджених операцій type_change/annul, не новий глобальний Audit Log для всіх кадрових форм.

Доступний автор береться з чинної дійсної персональної cookie-сесії; actor_id із HTTP body ігнорується. Без персональної сесії зберігається NULL і показується «Автор невідомий». Вільний режим не створює вигаданої особистості для цього аудиту. Чинна політика доступу staff API/Origin збережена, нові ролі або вимоги входу не додаються.

## Анулювання та архів

PersonEvent отримав annulled_at (DateTime UTC), annulment_reason (текст) та annulled_by (необов'язковий FK User). Неанульований запис має всі три поля NULL. Для анульованого обов'язкові точний час і непорожня причина. Причина обмежена 2000 символами на сервісному/UI-рівні.

POST `/persons/{person_id}/events/{event_id}/annul` приймає reason і expected_state. Сервіс перевіряє власника, знімок та відсутність попереднього анулювання, заповнює тільки три поля анулювання й додає correction=annul. Початкові date_start/date_end/planned_end/duration/тип/підтип та решта реквізитів не переписуються. Не створюється SERVICE, не підтверджується й не закривається інша подія.

Анулювання виключає запис із активних календаря, наявності, підсумків, фільтра типу, проблем та всіх репозиторних перевірок перетинів/автозавершення. Розрахункова служба після виключення можлива за попереднім правилом, без INSERT. Завершені події не є анульованими й лишаються в звичайній історії.

У правій панелі та спільному Modal нижче звичайних записів — згорнутий «Архів анульованих подій (N)». Показує початковий тип/підтип, період, причину, час і доступного автора; сірий стиль/позначка «Анульовано». У Modal доступна також історія виправлень, у панелі є перехід до неї. Звичайного редагування/повторного анулювання немає. Архів належить людині, не обмежується видимим періодом календаря. Відновлення анульованого запису цим завданням не реалізовано.

## Цілісність і транзакції

Обидві операції використовують попередню service_transaction(immediate=True) та порядок PostgreSQL FOR UPDATE Person → PersonEvent. Repository не commit. Зміна події й історія — одна атомарна операція; відмова INSERT аудиту відкочує все. Другий одночасний запис зі старим expected_state дає 409, без перезапису чужого рішення.

Фізичний DELETE PersonEvent заборонений також у старому сервісному/репозиторному методі й тригером БД. Нових DELETE-маршрутів немає. PersonEventCorrection append-only: UPDATE/DELETE заборонені тригерами. Анульовані PersonEvent незмінні на рівні БД. SQLite-guards існують лише для ізольованого legacy-тестування, PostgreSQL-guards встановлює Alembic.

## Міграція

Адитивна `0003_event_corrections` після `0002_event_completion`: три nullable-поля PersonEvent, FK/check, одна таблиця виправлень/індекс і чотири guard-тригери. Старі події не анулюються, реквізити та наявні підтвердження/плани не переписуються. Повторний `upgrade head` — no-op. Startup лише перевіряє поточний head, не мігрує автоматично.

Робоча БД у цьому завданні не мігрувалася. Після перевірки DATABASE_URL, зупинки застосунку й успішного backup (приклад pg_dump — в EVENT_CONTROL) окремо:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Linux: `.venv/bin/python -m alembic upgrade head`. Reset не потрібний. Downgrade із втратою анулювань/виправлень заборонений; відновлювати перевірену копію в окрему БД.

## Карта реалізації

| Файл | Зміна |
| --- | --- |
| models/person_event.py, models/event_correction.py | Метадані анулювання, окремі знімки історії та legacy guards. |
| repositories/event_repository.py | Активні/архівні вибірки, історія з автором, виключення анульованих із перетинів. |
| services/event_corrections.py | Знімки з назвами, запис/читання історії, точний UTC. |
| services/person_events.py, service_for_person_event.py | Намір зміни типу, знімок, анулювання, атомарність та заборона редагування архіву. |
| routers/person_events.py | Чинні POST, анулювання та необов'язковий справжній автор сесії. |
| services/event_views.py, event_rules.py | Сортування й архівний read view, незалежність від поточного обліку/контролю. |
| static/js/journal_controls.js, column_interactions.js | Адаптер спільного DnD; opt-in dragHandleSelector, попередні таблиці без зміни поведінки. |
| static/js/person_events.js, event_journal.js | Підтвердження/чернетки, архів, історія, заголовок підсумку й експорт. |
| templates/event_journal.html, components/person_events.html | Заголовки сортування, підтвердження й архівні елементи. |
| migrations/versions/0003_event_corrections.py | PostgreSQL-міграція, без автоматичного застосування до робочої БД. |

Перелік змінених файлів і фактичні результати запусків наведені нижче та в CURRENT_STATE.

## Повний перелік файлів цього етапу

Застосунок:

- `app/database/postgresql.py`
- `app/models/__init__.py`
- `app/models/event_correction.py`
- `app/models/person_event.py`
- `app/repositories/event_repository.py`
- `app/routers/person_events.py`
- `app/services/event_corrections.py`
- `app/services/event_rules.py`
- `app/services/event_views.py`
- `app/services/person_events.py`
- `app/services/service_for_person_event.py`
- `app/static/css/event_views.css`
- `app/static/js/column_interactions.js`
- `app/static/js/event_journal.js`
- `app/static/js/journal_controls.js`
- `app/static/js/person_events.js`
- `app/templates/components/person_events.html`
- `app/templates/event_journal.html`

Міграція:

- `migrations/versions/0003_event_corrections.py`

Тести:

- `tests/browser/column_visibility.cjs`
- `tests/browser/event_corrections.cjs`
- `tests/browser/journal.cjs`
- `tests/postgresql/test_event_corrections.py`
- `tests/test_event_corrections.py`
- `tests/test_service_transactions.py`

Документація:

- `docs/ARCHITECTURE.md`
- `docs/CURRENT_STATE.md`
- `docs/EVENT_CONTROL.md`
- `docs/EVENT_CORRECTIONS.md`
- `docs/EVENT_VIEWS.md`
- `docs/PERSON_EVENTS.md`
- `docs/POSTGRESQL_SETUP.md`
- `docs/TABLE_UI.md`

## Уточнення представлення журналу

Склад/посади тепер визначає незалежний as_of, а не кінець календарного періоду; без офіційного призначення людина не показується. start/end не обрізають її події датами призначення/версії. Сортування, confirmed type change, append-only аудит й анулювання не переписані. Header menus використовують спільні value_filter/QueryFilterAdapter, text/cell selection і Wrap Text описані в [EVENT_VIEWS.md](EVENT_VIEWS.md). Подальша 0004 — лише актуалізація довідника DAY_OFF/VLK, без зміни таблиць виправлень.
