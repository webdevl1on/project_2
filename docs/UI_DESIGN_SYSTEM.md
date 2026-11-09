# Єдина дизайн-система project_2

Реалізація у `feature/security`, база **cea24ab**. Орієнтири: `01_sidebar_open_closed.webp` визначає overlay-навігацію й ієрархію, `02_three_themes_open_closed.webp` — три палітри однакових компонентів. Інші зображення використано для компонування відповідних розділів; вигадані поля, користувачі, повідомлення, глобальний пошук, звіти та workflow з ілюстрацій не переносилися.

## Оболонка та охоплення

`templates/layouts/base.html` надає єдиний HTML-документ, early theme script, Bootstrap **5.3.8** із SRI, спільні стилі, персональний CSRF/session script, верхню панель, overlay sidebar, breadcrumbs і робочу область. `layouts/auth.html` успадковує ту саму основу з компактним оформленням входу/MFA. Дубльовані Bootstrap/навігацію/метадані видалено зі сторінок. Сторінкові скрипти, їхній порядок, форми та необхідні CSS залишено.

39 повних шаблонів використовують inheritance. Фрагменти відповідей contacts/geography/overview/assignment audit залишаються фрагментами, отримують тему від батьківського документа; повторну оболонку в AJAX не вставляти. `search_person.html` та `admin/login.html` — legacy без активних HTML-обробників; вони також адаптовані, маршрути для них не створювалися. Чинний `/admin/login` залишається захищеним перенаправленням.

| Сторінки / наявні форми | Шаблони |
| --- | --- |
| `/persons`, `/persons/new`, `/persons/{id}/created`, `/persons/{id}/edit` | `persons`, `person_create`, `person_created`, `person_form` |
| `/person_detail/{id}`, `/person_full_info/{id}`, персональні відмінки | `person_detail`, `person_full_info`, **`person_access`** для scoped-проєкції, `person_name_cases`; усі наявні компоненти вкладок |
| `/person-positions`, `/staff/history`, preview імпорту, помилка кадрової операції | `person_positions`, `staff_history`, `staff_import_preview`, `staff_error` |
| `/events`, `/events/problems`, редактори подій | `event_journal`, `event_problems`, чинні `components/person_events`, `journal_header`, `event_badge` |
| `/admin`, `/admin/staff`, словники та Excel | `admin/index`, `staff`, `dictionaries`, `dictionary_form`, `import_preview`, `error` |
| `/admin/tcc`, `/admin/tcc/new`, редагування та preview | `admin/tcc`, `tcc_form`, `tcc_preview` |
| `/admin/organization`, `/admin/organization/staff` | `admin/organization`, `organization_staff` |
| `/admin/users`, `/admin/users/new`, деталізація й аудит | `admin/users`, `user_new`, `user_detail`, `account_audit` |
| `/admin/access`, `/admin/backups` | `admin/access`, `backups` |
| `/auth/login`, `/auth/mfa`, власна безпека/пароль/сесії | `login`, `mfa`, `account_security`, `account_password`, `account_sessions` |
| `/docs`, `/redoc` | Спільний `api_docs`; офіційні Swagger UI/ReDoc у тій самій захищеній оболонці |

Root layout забезпечує один main landmark: для старих сторінок з власним `<main>` оболонка має presentation role, для решти — main. Є skip link, видимий клавіатурний фокус, горизонтальна прокрутка вкладок і таблиць у власних viewport.

## Tokens та теми

- `static/css/design_tokens.css`: семантичні кольори background/surface/text/border/primary/focus, success/warning/danger/info, парні кольори статусів, spacing, радіуси, тіні, висота header.
- `themes.css`: **light**, **dark**, **military** та зв’язок із `--bs-*`. Dark має власні поверхні й текст; інверсії/filter немає. Military використовує оливкову панель/меню, світлу нейтральну область і оливковий primary.
- `ui_components.css`: спільне оформлення Bootstrap-компонентів, форм, карток, alerts, таблиць, modal, status, record panes та документаційних widgets.
- `ui_layout.css`: topbar, overlay sidebar, workspace, auth, адаптивні сітки, profile/record layout.
- Старі `app_layout`, `event_views`, `access`, `organization`, `staff_history`, `column_visibility` зберігають предметну геометрію/поведінку; жорсткі кольори переведено на semantic tokens.

Статуси подій мають парні `--tone-<code>-bg/text` у кожній темі. Власні заливки таблиць зберігають **ті самі** п’ять кольорів і контракт сховища; для них явно задано темний текст/посилання. Виділення поверх заливки має окрему тематичну пару. Не змінювати палітру користувача при перемиканні теми.

## Перемикач та зберігання

`static/js/theme_manager.js` синхронно виконується **до стилів**, виставляє `html[data-theme]` і `data-bs-theme`. Bootstrap mode: dark для dark, light для light/military. Початковий HTML має light; невідоме/пошкоджене значення або недоступний storage дає light. JS не чекає DOMContentLoaded для першого застосування, що запобігає спалаху іншої теми.

Ключ **`project2:ui-theme`** — простий код теми в localStorage. Вибір у меню користувача застосовується негайно без reload, синхронізується між вкладками storage event. Меню доступне також без персональної сесії на вході й MFA, але не показує захищених переходів. Помилка запису не блокує сторінку, повідомляє, що вибір не збережено.

`ProjectTheme` має normalize/read/apply/set, реєстр `themes`, `bootstrapModes` і `useAdapter({read,write})`. Селект заповнюється реєстром, а не окремою клієнтською копією списку. Майбутній профільний adapter може використовувати кешований серверний вибір і власне збереження; зараз нових API/таблиць/міграцій немає. Подія `project2:theme-change` містить лише `{theme,saved}` та за потреби джерело storage, без особистих даних.

### Четверта тема

Додайте семантичні overrides у `themes.css` під `html[data-theme=<code>]`, назву до `themes` та light/dark mode до `bootstrapModes` у `theme_manager.js`. Наявні шаблони, контролери таблиць та серверні маршрути **не змінюються**: селект автоматично одержує новий пункт. Перевірте звичайні/disabled/focus стани, Bootstrap, статуси, user fills та всі чотири ширини. Палітра повинна мати достатній контраст; не використовуйте довільні значення зі storage як CSS.

## Навігація

`components/app_navigation.html` і `navigation.js` використовують **Bootstrap Offcanvas**, а не нову реалізацію focus trap. Меню закрите за замовчуванням на всіх ширинах, накладається зліва, має backdrop, закривається кнопкою, Escape, фоном і переходом. `data-bs-scroll=true` не прибирає scrollbar сторінки, тому ширина та координати таблиць не змінюються. Перед відкриттям закриваються відкриті dropdown/popover; Bootstrap відновлює фокус.

Посилання ведуть лише на наявні сторінки. Адміністрування доступне в меню тільки Master/Admin, делегованій матриці User відповідає окремий дозволений перехід. `ui_org_visible` у спільному `security_context` — лише UI boolean з **чинного** evaluator.read для реальних підрозділів; серверних правил не додає. Основні scoped-списки залишаються дозволеними HTML-маршрутами з серверно відфільтрованими даними. Меню не є захисною межею: прямі HTTP/API/file requests як і раніше перевіряє сервер.

## Компоненти та нові сторінки

`components/ui.html`: breadcrumbs, page_header, card, summary_card, filter_toolbar, search_field, form_group, section_header, tabs, status, alert, table_wrapper, empty_state, loading_state, restricted, button, attachment. `ui_panels.html`: Bootstrap modal, confirm_dialog з CSRF, detail_panel. Іконки — локальний SVG macro `ui_icons.html`, без нового icon/font framework.

Мінімальне підключення:

```jinja2
{% extends 'layouts/base.html' %}
{% from 'components/ui.html' import page_header,card,status %}
{% block title %}Реалізований розділ{% endblock %}
{% block content %}
{{ page_header('Реалізований розділ','Короткий контекст') }}
{% call card('Відомості') %}{{ status('Підтверджено','success') }}{% endcall %}
{% endblock %}
```

Для форми використовуйте `form_group(label,for_id)` з власним унікальним input.id і чинним серверним action/CSRF. Не додавайте власні копії date input, Person Picker, upload або session/MFA. `tabs` використовує Bootstrap: ID panel — `<tabs-id>-<key>`. Складні чинні вкладки анкети зберігають старі ID й обробники. `attachment` отримує URL **захищеного file endpoint**, а не шлях файлової системи чи URL з невалідованого введення.

У content передавайте лише вже авторизований DTO; macros не визначають дозволи. Повідомлення й labels автоматично екрануються; не додавайте `safe` до користувацьких значень. Для форми/панелі успадковуйте поточний workflow і validators; тему змінюйте tokens, а не inline кольорами.

## Анкета та записи

Header Admin-анкети розділяє ПІБ, звання, підставу служби, офіційну посаду й підрозділ; відсутня фотографія залишається чесною заглушкою. Компактний огляд містить особисті/службові/контактні/адресні картки, медичні відомості, переходи до документів та інших наявних категорій. Статуси/дати не вигадуються. На вкладці подій повторно підключено вже наявний PersonEvents modal замість старого повідомлення про розробку.

`profile_layout.js` змінює порядок/видимість **лише дозволених сервером DOM-блоків**, доступними кнопками ↑/↓ і checkbox. Ключ `project2:profile-layout:v1`: version=1, order/hidden — лише назви блоків. Person/user IDs, реквізити та права не зберігаються. Невідомі ключі відкидаються, нові дозволені блоки додаються в стандартному порядку. Налаштування застосовуються після AJAX refresh огляду; є reset. Вони спільні для цього браузерного профілю, не є серверними персональними налаштуваннями.

`record_panels.js` представляє існуючі details як список + вибрані реквізити на ширині ≥1100 px; нижче — звичайне розгортання під записом. Кнопки/форми/файли **переміщуються разом з оригінальними вузлами**, не клонуються. Значення й handlers зберігаються; окремих запитів або нової CRUD-логіки немає. Архів документів залишається окремим нижнім блоком. У `medical.js` адаптовано лише два DOM-селектори пошуку розгорнутих вкладень до спільної оболонки.

### ACL

`person_access.html` зберігає всі вихідні `access_rights` умови й read-only секції. Якщо категорія заборонена, немає її блоку, skeleton, placeholder чи запису у налаштуванні огляду. Заборонені значення не додаються до HTML, JSON, атрибутів або storage. Картка не відновлюється налаштуванням, якщо її немає в дозволеному DOM.

Macro `restricted(label)` підтримує замок і «Доступ обмежено» **лише коли сервер дозволив показ назви поля**. Чинна проєкція не надає окремого реєстру дозволених назв для прихованих полів усередині категорій; автоматичні locked-картки на цій основі не вигадувалися. Якщо потрібне детальніше field-level відображення, залежність — окремо погоджені безпечні UI-метадані сервера, а не послаблення ACL.

## Таблиці, форми та адаптивність

Чинні column visibility/order/drag/resize, presets, filters, sorting, Undo/Redo, cell/row/column selection, Excel/Word copy, fills, row height/fonts/scale, sticky headers, Міражі та assignment workflows повторно використані. Їхні storage keys/формати не змінено. Великі таблиці мають власні viewport, меню не змінює їхньої ширини. Старий `staff_history` збережено як історію посад/призначень з усіма revision/audit діями.

Картки, форми, дати, dropdown, filter panels, file lists і modal мають спільні поверхні/межі/focus стани. На телефоні форми й огляд одноколонкові, кнопки не ховаються без альтернативи. Перевірки виконуються на **390, 768, 1280, 1920 px**. `prefers-reduced-motion` скорочує анімації. Нативні file chooser/calendar/prompt/confirm та OS-діалоги WebAuthn використовують оформлення браузера/ОС; їхні робочі сценарії не переписувалися.

Swagger/ReDoc використовують офіційні widgets у спільному layout, ті самі URL й захист. Їхні палітри адаптує `api_docs.js`/CSS; переоформлення ReDoc зберігає введений пошуковий текст. Ці технічні widgets не стають SPA-фреймворком предметних сторінок.

## Перевірки й межі

`tests/ui_template_contracts.json` — інвентар вихідних id/name/data-* і локальних скриптів без даних БД. Тест перевіряє їх збереження у сторінці або спільній оболонці; окремо виявлено й відновлено історичний script після `</body>` у person_form. Нові Python-тести перевіряють inheritance, escaping, ролі/CSRF та scoped DOM; Node — theme registry/storage/fallback/Bootstrap mode/adapter; Chromium — навігацію, геометрію, теми, записи, drafts, профіль, мобільні сторінки й технічні widgets. Повні фактичні результати — [CURRENT_STATE.md](CURRENT_STATE.md).

Не змінено ORM, Alembic, PostgreSQL DDL, предметні сервіси, ролі, ACL evaluator, MFA/CSRF/session policy, файлове сховище або API CRUD-контракти. Python-зміни лише у `templating.security_context` (UI boolean) та HTML-відповідях двох технічних маршрутів `/docs`/`/redoc`; URL, захисні залежності й OpenAPI залишаються чинними. Робочі дані, reset, міграції, commit/push/merge не використовувалися. Додаткових виробничих залежностей немає.

Chromium перевіряється на синтетичних даних; Firefox/Safari, реальні сенсорні пристрої, системний high-contrast і виробничі величезні набори не вимірювалися. Стабільні зовнішні Bootstrap/Swagger/ReDoc CDN залишаються потрібними як і раніше; автоматизовані тести відтворюють справжні assets. Конструктор рапортів, новий workflow погодження, вигадані сторінки з референсів і серверне збереження UI-профілю поза цим завданням.

## Змінені файли

Повний перелік цього UI-етапу — **85 файлів**. Попередніх сторонніх змін у початковому дереві не було; commit/push не виконано.

<details><summary>Шаблони, компоненти, стилі, скрипти, тести та документація</summary>

```text
app/main.py
app/static/css/access.css
app/static/css/app_layout.css
app/static/css/column_visibility.css
app/static/css/design_tokens.css
app/static/css/event_views.css
app/static/css/organization.css
app/static/css/person_picker.css
app/static/css/staff_history.css
app/static/css/themes.css
app/static/css/ui_components.css
app/static/css/ui_layout.css
app/static/js/api_docs.js
app/static/js/medical.js
app/static/js/navigation.js
app/static/js/profile_layout.js
app/static/js/record_panels.js
app/static/js/theme_manager.js
app/templates/account_password.html
app/templates/account_security.html
app/templates/account_sessions.html
app/templates/admin/access.html
app/templates/admin/account_audit.html
app/templates/admin/backups.html
app/templates/admin/dictionaries.html
app/templates/admin/dictionary_form.html
app/templates/admin/error.html
app/templates/admin/import_preview.html
app/templates/admin/index.html
app/templates/admin/login.html
app/templates/admin/organization.html
app/templates/admin/organization_staff.html
app/templates/admin/staff.html
app/templates/admin/tcc.html
app/templates/admin/tcc_form.html
app/templates/admin/tcc_preview.html
app/templates/admin/user_detail.html
app/templates/admin/user_new.html
app/templates/admin/users.html
app/templates/api_docs.html
app/templates/components/app_navigation.html
app/templates/components/ui.html
app/templates/components/ui_icons.html
app/templates/components/ui_panels.html
app/templates/event_journal.html
app/templates/event_problems.html
app/templates/layouts/auth.html
app/templates/layouts/base.html
app/templates/login.html
app/templates/mfa.html
app/templates/person/components/full_info_top_navigation.html
app/templates/person/components/names_history.html
app/templates/person/components/overview_controls.html
app/templates/person/components/profile_header.html
app/templates/person/components/profile_overview.html
app/templates/person/components/profile_photo.html
app/templates/person/components/rank_history.html
app/templates/person_access.html
app/templates/person_create.html
app/templates/person_created.html
app/templates/person_detail.html
app/templates/person_form.html
app/templates/person_full_info.html
app/templates/person_name_cases.html
app/templates/person_positions.html
app/templates/persons.html
app/templates/search_person.html
app/templates/staff_error.html
app/templates/staff_history.html
app/templates/staff_import_preview.html
app/templating.py
docs/ARCHITECTURE.md
docs/CURRENT_STATE.md
docs/TABLE_UI.md
docs/UI_DESIGN_SYSTEM.md
tests/browser/column_visibility.cjs
tests/browser/security.cjs
tests/browser/staff.cjs
tests/browser/ui_api.cjs
tests/browser/ui_design.cjs
tests/browser/workspace.cjs
tests/js/theme_manager.test.cjs
tests/test_table_workspace.py
tests/test_ui_design.py
tests/ui_template_contracts.json
```

</details>
