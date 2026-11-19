# Промпт для Codex: Security 1.8 — сертифікати пристроїв (mTLS) і HSTS

> Повідомлення для Codex (скопіюйте як є):
>
> ```
> Репозиторій webdevl1on/project_2. Створи гілку codex/security18-device-certs від актуальної feature/security.
> Виконай завдання з файлу docs/codex/SECURITY18_DEVICE_CERTS.md (усе нижче лінії) і дотримуйся AGENTS.md.
> Наприкінці зроби коміт і запуш у гілку codex/security18-device-certs.
> Не пуш у feature/security, testing чи main, не зливай гілки й не створюй PR.
> У фінальному повідомленні дай звіт за розділом «Звіт наприкінці».
> ```

---

## Контекст

`project_2` — FastAPI + PostgreSQL на Windows. Security 1.7 уже працює на реальних ПК: сервер `foxlys`, `python -m app.serve`, прямий HTTPS `https://foxlys.local:8443`, власний серверний CA з Name Constraints, фільтр підмереж `LanMiddleware`, Task Scheduler. Дотримуйся `AGENTS.md`. Прочитай лише:

- `docs/SECURITY.md` — розділи «Security 1.7 — LAN», «HTTPS і локальна розробка»;
- `docs/PRODUCTION_START.md` — розділ «Етап LAN»;
- код: `app/serve.py`, `app/security/network.py` (`NetworkSettings`, `tls_file`, `protected_paths`), `app/security/lan.py` (`LanMiddleware`), `app/main.py` (підключення middleware);
- скрипти: `scripts/lan/Project2Lan.psm1`, `scripts/lan/Test-Project2Lan.ps1`, `scripts/lan/Install-Project2ClientCA.ps1`;
- тести: `tests/test_lan.py`, `tests/test_lan_scripts.py`, `tests/conftest.py`.

## Мета

Зараз будь-який ПК у дозволеній підмережі бачить сторінку входу, і браузер дозволяє обійти помилку сертифіката. Потрібно:

1. **mTLS.** Сервер у LAN-режимі приймає TLS-з'єднання **лише** від ПК із чинним сертифікатом пристрою, виданим окремим **Device CA**. Без сертифіката, з чужим, простроченим чи відкликаним — TLS-рукостискання відхиляється, жодна HTTP-сторінка не віддається. Сервер-ПК також потребує сертифікат, винятків немає.
2. **Відкликання** через CRL: загублений ПК відкликається однією командою, після перезапуску сервера він не підключиться.
3. **HSTS** на всіх HTTPS-відповідях.

Ключ пристрою зберігається у Windows на конкретному ПК як **неекспортований** (`Cert:\CurrentUser\My`). Пароль/MFA-вхід лишається без змін — mTLS є додатковим першим рівнем.

## Вимоги

### 1. Device CA і видача сертифікатів — Python CLI `python -m app.security.device_ca`

Операції з CA робимо на Python (`cryptography`, уже в залежностях), а не в PowerShell: це тестується в CI і дає повноцінний CRL. Команди:

- `init --dir <каталог>` — створює **окремий** Device CA: EC P-256 або RSA 3072, `CN=Project 2 Device CA`, `basicConstraints CA:true pathlen:0` critical, `keyUsage keyCertSign,cRLSign` critical, строк 10 років. Приватний ключ — лише PKCS#8 PEM, зашифрований паролем (`BestAvailableEncryption`). Пароль — через `getpass`, з підтвердженням, мінімум 12 символів; ніколи з аргументів чи змінних середовища. Створює порожній CRL і реєстр `devices.json`. Відмовляє, якщо каталог уже містить CA.
- `issue --dir <каталог> --name <pc-name> --out <файл.pfx>` — видає сертифікат пристрою: новий ключ EC P-256, `CN=<pc-name>`, `O=Project 2 Devices`, випадковий 128-бітний serial, `basicConstraints CA:false` critical, `keyUsage digitalSignature` critical, `extendedKeyUsage clientAuth`, строк 730 днів (не довше строку CA), AKI/SKI. Вихід — PKCS#12 з **окремим** паролем (запит через `getpass`), шифрування AES-256 + SHA-256 (`PrivateFormat.PKCS12.encryption_builder()`), без сертифіката CA всередині. `--name`: `[a-z0-9-]{1,40}`, унікальне серед чинних записів. Запис у `devices.json`: name, serial (hex), виданий, діє до, SHA-256 сертифіката, статус.
- `revoke --dir <каталог> (--name <pc-name> | --serial <hex>) --reason <keyCompromise|superseded|cessationOfOperation>` — позначає в реєстрі та **перевипускає CRL** (номер CRL зростає, `nextUpdate` = зараз + 400 днів).
- `crl --dir <каталог>` — перевипускає CRL без змін списку (планове поновлення).
- `list --dir <каталог>` — таблиця пристроїв і стан CRL (дата `nextUpdate`).
- Для всіх змінних команд — пароль CA через `getpass`; атомарний запис (тимчасовий файл + rename); каталог не може бути в репозиторії, `static` чи сховищах даних (повторно використай перевірки з `network.py`).
- Файли в каталозі: `device-ca.key.pem` (зашифрований), `device-ca.crt.pem`, `device-ca.crl.pem`, `devices.json`. Типовий каталог у документації — `C:\project2-secrets\device-ca\`. Сервер читає тільки `.crt.pem` і `.crl.pem`.

### 2. Сервер: обов'язковий mTLS у LAN

Нові змінні (документувати в `config/production.env.example`, `config/development.env.example`):

- `PROJECT2_CLIENT_CA` — шлях до `device-ca.crt.pem`;
- `PROJECT2_CLIENT_CRL` — шлях до `device-ca.crl.pem`.

Правила в `NetworkSettings.read`:

- якщо bind не loopback (LAN) — обидві змінні **обов'язкові**; відсутність → помилка старту з поясненням. Вимкнути mTLS для LAN не можна;
- файли — поза репозиторієм/static/сховищами (як `tls_file`);
- `PROJECT2_CLIENT_CA` — сертифікат CA (`basicConstraints CA:true`, `keyCertSign`), чинний на момент старту; не може бути тим самим CA, що підписав серверний сертифікат;
- CRL підписаний цим CA; якщо `nextUpdate` уже минув → помилка старту з командою поновлення (`python -m app.security.device_ca crl ...`); якщо до `nextUpdate` менше 30 днів → попередження в стартовому рядку і в журналі.

`app/serve.py`: передай `uvicorn.run(..., ssl_context_factory=...)` (є в uvicorn 0.49). Фабрика бере стандартний контекст від uvicorn і додає: `load_verify_locations(cafile=PROJECT2_CLIENT_CA)`, `load_verify_locations(cafile=PROJECT2_CLIENT_CRL)`, `verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF`, `verify_mode = ssl.CERT_REQUIRED`, `minimum_version = TLSv1_2`. Довіряй **лише** Device CA для клієнтів (не системному сховищу). Стартовий рядок додатково показує: `mTLS: Device CA <SHA-256 скорочено>, CRL до <дата>, відкликано <N>`.

Loopback-режим (`PROJECT2_BIND_HOST=127.0.0.1`, локальна розробка й аварійний доступ на сервер-ПК через `http://localhost:8000` з `PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1`) — без mTLS, як зараз.

### 3. HSTS

У `LanMiddleware` для кожної HTTPS-відповіді (включно з 4xx/5xx і static) додавай `Strict-Transport-Security: max-age=31536000` — без `includeSubDomains` і `preload`. Для HTTP-відповідей на loopback — не додавати. Не дублювати, якщо заголовок уже є.

### 4. PowerShell (Windows PowerShell 5.1, UTF-8 з BOM, `[CmdletBinding()]`, `-WhatIf` для змін, українські повідомлення)

1. `scripts/lan/Install-Project2DeviceCert.ps1 -PfxPath <файл> [-ExpectedSha256 <hex>]` — на клієнті під **тим користувачем Windows, який працюватиме в браузері** (не обов'язково адміністратор): імпорт у `Cert:\CurrentUser\My` через `Import-PfxCertificate` **без** `-Exportable` (ключ неекспортований); пароль PFX через `Get-Credential`/`Read-Host -AsSecureString`; перевірка, що це сертифікат з EKU clientAuth і що він не прострочений; показ CN, строку і SHA-256; якщо задано `-ExpectedSha256` — звірка. Після успіху пропонує безпечно видалити PFX-файл (підтвердження). Якщо в сховищі вже є сертифікат пристрою від того ж Device CA — повідомити й не дублювати.
2. `scripts/lan/Remove-Project2DeviceCert.ps1` — видаляє з `CurrentUser\My` сертифікати пристрою Project 2 (з ключем), з підтвердженням.
3. `scripts/lan/Restart-Project2Task.ps1` — перезапуск задачі `Project2-LAN` (для застосування нового CRL), з перевіркою статусу після старту.
4. `Test-Project2Lan.ps1` — оновити: шукає в `CurrentUser\My` сертифікат з EKU clientAuth, `O=Project 2 Devices`, чинний; передає його в `SslStream.AuthenticateAsClient(host, certs, Tls12|Tls13, $false)`; якщо сертифіката немає — зрозуміле повідомлення «На цьому ПК немає сертифіката пристрою Project 2 → Install-Project2DeviceCert.ps1»; якщо сервер відхилив — підказка про відкликання/строк. Перевіряє наявність заголовка HSTS у відповіді.

Скрипти не містять паролів, IP-адрес, імен користувачів, окрім параметрів за замовчуванням `foxlys.local`/`8443`/`Project2-LAN`.

### 5. Тести

- **CLI Device CA** (`tests/test_device_ca.py`): init/issue/revoke/crl/list на тимчасовому каталозі з підміненим `getpass`; ключ CA зашифрований (без пароля не завантажується); PFX відкривається тільки з паролем і не містить CA; поля сертифіката (EKU clientAuth, CA:false, CN, O, строк ≤ CA); унікальність імені; revoke збільшує номер CRL і містить serial; відмова в каталозі всередині репозиторію; повторний init відхиляється.
- **Справжній TLS** (`tests/test_mtls.py`): uvicorn з фабрикою контексту на `127.0.0.1` та ефемерному порту у фоновому потоці (або `ssl`-сервер з тим самим контекстом); клієнт `ssl`/`httpx`:
  - чинний сертифікат пристрою → 200 на `/auth/login`, є HSTS;
  - без сертифіката → помилка рукостискання, HTTP-відповіді немає;
  - сертифікат від іншого CA, у т.ч. від **серверного** CA → відмова;
  - відкликаний (після `revoke` і нового контексту) → відмова; інший чинний пристрій працює;
  - сертифікат пристрою з простроченим строком → відмова.
- **Налаштування**: LAN без `CLIENT_CA`/`CLIENT_CRL` → помилка; прострочений CRL → помилка; CRL від чужого CA → помилка; `CLIENT_CA` = серверний CA → помилка; < 30 днів до `nextUpdate` → попередження; loopback працює без цих змінних.
- **HSTS**: присутній на HTTPS (200, 303, 403, 404, static), відсутній на loopback HTTP.
- **PowerShell**: розбір нових скриптів (якщо є `pwsh`); оновити очікувану кількість скриптів у `test_all_lan_scripts_parse_and_windows_powershell_reads_ukrainian`.
- Усі наявні тести мають пройти: `python -m pytest tests/ -q` на ізольованій SQLite і `tests/postgresql/` на `project2_ci`, якщо PostgreSQL доступний. **Не запускай** `reset.py`, `reset_test_db.py`, кореневі `test*.py`.

### 6. Документація (українською, стисло)

- `docs/PRODUCTION_START.md` — новий розділ **«Сертифікати пристроїв (mTLS)»** із точним **порядком переходу**, щоб не втратити доступ:
  1. на сервері: `device_ca init`, видати PFX для **кожного** ПК, включно з `foxlys`;
  2. на кожному ПК (і на сервері) під користувачем браузера: `Install-Project2DeviceCert.ps1`, передача PFX флешкою, пароль PFX — окремим каналом; після імпорту PFX видалити з флешки;
  3. лише після цього — додати `PROJECT2_CLIENT_CA`/`PROJECT2_CLIENT_CRL` у `.env` і `Restart-Project2Task.ps1`;
  4. перевірка `Test-Project2Lan.ps1` на кожному ПК; браузер при першому відкритті просить вибрати сертифікат.
  
  Також: загублений/виведений ПК → `revoke` → `Restart-Project2Task.ps1`; новий ПК → `issue`; щорічне поновлення CRL (`crl`) і нагадування за 30 днів; поновлення сертифіката пристрою через 2 роки; Firefox використовує сертифікати Windows (`security.osclientcerts.autoload`, типово увімкнено в сучасних версіях) — перевірити; **аварійний доступ** на сервер-ПК, якщо mTLS зламався: зупинити задачу, тимчасово запустити loopback-режим (`PROJECT2_BIND_HOST=127.0.0.1`, `PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1`, адреса `http://localhost:8000`), виправити, повернути LAN-налаштування.
- `docs/SECURITY.md` — розділ «Security 1.8 — сертифікати пристроїв і HSTS»: модель загроз (чужий ПК у LAN, обхід попередження браузера, викрадений ноутбук, копіювання ключа), що перевіряється і де, межі (mTLS прив'язаний до ПК+користувача Windows, а не до особи; вхід/MFA лишаються обов'язковими).
- `docs/ARCHITECTURE.md` — навігація; місце mTLS у потоці (TLS-рукостискання до `LanMiddleware`).
- `docs/CURRENT_STATE.md` — що реалізовано, що фактично перевірено, що **не** перевірено (Windows `Import-PfxCertificate`, вибір сертифіката в Chrome/Edge/Firefox, неекспортованість ключа, перезапуск задачі).

## Межі

- Не змінюй моделі БД, міграції, логіку ролей, ACL, MFA, резервування, серверний CA і Name Constraints з 1.7.
- Без NSSM, реверс-проксі, сторонніх утиліт (OpenSSL на Windows не потрібен).
- Не коміть сертифікати, ключі, PFX, CRL, `devices.json`, `.env`.
- Не пуш нікуди, крім `codex/security18-device-certs`. Повідомлення коміту: `feat(security): Security 1.8 device certificates (mTLS) and HSTS`.

## Звіт наприкінці

Список змінених файлів; фактично запущені команди з результатами (passed/failed/skipped); що не перевірено і чому; відкриті питання.
