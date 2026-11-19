# Запуск Project 2 на Windows

Покрокова інструкція першого запуску production з нуля на ПК, який згодом стане LAN-сервером. Детальні пояснення — [POSTGRESQL_SETUP.md](POSTGRESQL_SETUP.md), безпека — [SECURITY.md](SECURITY.md), резервування — [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md).

Для першого входу на сервері використовуйте `http://localhost:8000`. Порядок відкриття `https://foxlys.local:8443` для клієнтських ПК наведено в розділі «Етап LAN».

## 0. Передумови

- Windows 10/11 x64, Python 3.12+, Git, PostgreSQL **17** x64 з Command Line Tools (офіційний інсталятор).
- Під час встановлення PostgreSQL: порт 5432, `listen_addresses='localhost'` (типово). Пароль `postgres` збережіть у менеджері паролів.
- Робоча версія запускається з гілки `main` в **окремому каталозі** (не в тому, де ведеться розробка):

```powershell
git clone -b main https://github.com/webdevl1on/project_2 C:\project2-prod
cd C:\project2-prod
```

## 1. Python-середовище

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 2. Секрети

```powershell
python scripts/generate_production_secrets.py
```

Скрипт лише друкує значення: `STAFF_SIGNING_KEY`, `PROJECT2_MFA_KEYS`, пароль ролі БД. **Одразу збережіть їх офлайн** (менеджер паролів + зашифрований USB). Втрата `PROJECT2_MFA_KEYS` = неможливість входу з TOTP; втрата `STAFF_SIGNING_KEY` ламає перевірку підписаних даних. Ключі не змінюйте після старту без процедури ротації (SECURITY.md, «Конфігурація, backup та ротація ключів»).

## 3. Роль і БД PostgreSQL

```powershell
$env:Path = "C:\Program Files\PostgreSQL\17\bin;" + $env:Path
psql -h 127.0.0.1 -U postgres -d postgres -W
```

```sql
CREATE ROLE project2_prod LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password project2_prod
CREATE DATABASE project2_prod OWNER project2_prod ENCODING 'UTF8';
REVOKE ALL ON DATABASE project2_prod FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE project2_prod TO project2_prod;
\q
```

Для `\password` використайте пароль зі скрипта. Ролі `project2_dev`/`project2_ci` (розробка й тести) — за POSTGRESQL_SETUP.md, розділ «Windows 10».

## 4. Каталоги даних

```powershell
'documents','photos','temporary','exports','backups' | ForEach-Object { New-Item -ItemType Directory -Force -Path ("C:\project2-data\production\" + $_) | Out-Null }
```

Каталоги — поза репозиторієм. Рекомендовано диск із BitLocker.

## 5. Файл `.env`

```powershell
Copy-Item config/production.env.example .env
notepad .env
```

Замініть `CHANGE_ME` у `DATABASE_URL` паролем ролі, вставте `STAFF_SIGNING_KEY` і `PROJECT2_MFA_KEYS` зі скрипта. На етапі «тільки сервер-ПК»:

```
PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1
PROJECT2_WEBAUTHN_RP_ID=localhost
PROJECT2_WEBAUTHN_ORIGINS=["http://localhost:8000"]
```

`.env` ігнорується Git — не публікуйте його й не надсилайте в чат.

## 6. Схема, довідники, перший адміністратор

```powershell
python -m alembic upgrade head
python -m alembic current
python -c "from app.database.db import engine; from app.database.schema_check import require_current_schema; require_current_schema(engine); print('Schema OK'); engine.dispose()"
python -m app.services.mfa_keys --initialize
python -m app.services.seed_postgresql --dry-run --allow-production
```

`mfa_keys --initialize` — одноразовий запис контрольного значення ключа MFA; без нього сервер не стартує («Спочатку виконайте ... --initialize»). Повторний запуск лише перевіряє ключ.

Перегляньте звіт dry-run; якщо конфліктів немає — та сама команда без `--dry-run`. Додаткові джерела (`--names`, `--geography`, `--tcc`, `--staff-excel`) — POSTGRESQL_SETUP.md, «Безпечне засівання довідників».

```powershell
python -m app.services.bootstrap_account --username first-admin --display-name "Адміністратор"
```

Пароль запитується приховано. Bootstrap — **одноразово**; інших користувачів створює адміністратор у `/auth/users`.

## 7. Запуск і перший вхід

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Відкрийте саме `http://localhost:8000/persons` (не `127.0.0.1` — origin WebAuthn має збігатися з `.env`). Увійдіть і налаштуйте MFA.

**Важливо щодо MFA на цьому етапі:** використовуйте **TOTP** (застосунок-автентифікатор) і збережіть резервні коди. Апаратні ключі/Windows Hello, зареєстровані для `localhost`, не працюватимуть після переходу на LAN-ім'я в 1.7 — їх доведеться зареєструвати заново. TOTP і резервні коди переходять без змін.

## 8. Перевірка тестами (один раз, на тестовій БД)

Тести запускаються **не на production**: окрема роль/БД `project2_ci` і окремий `.env`/змінні процесу (POSTGRESQL_SETUP.md, «Тести»). Фікстури перестворюють таблиці тестової БД. Результати запусків для Security 1.7 наведено в [CURRENT_STATE.md](CURRENT_STATE.md).

## 9. Резервування

До внесення значного обсягу даних налаштуйте резервні копії за [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md) і [SECURITY16_REPORT.md](SECURITY16_REPORT.md#налаштування-windows-перед-використанням): окремі keyring, `PROJECT2_BACKUP_CONFIG`, worker у Task Scheduler, перший реальний drill.

## Етап LAN

Адреса для сервера `foxlys` та всіх восьми клієнтів — **`https://foxlys.local:8443`**. PostgreSQL працює на loopback сервера. Застосуйте ці кроки в каталозі версії, що містить `app/serve.py` та `scripts/lan/`.

### На сервері

1. До переходу перевірте вхід за TOTP або наявність невикористаного резервного коду, особливо для Master. Вони працюють після зміни імені. Passkey, апаратний FIDO2-ключ і Windows Hello прив’язані до RP ID. Після входу на `foxlys.local` зареєструйте їх для нового імені у «Безпеці облікового запису».
2. У корені репозиторію оновіть залежності та створіть локальний CA і серверний сертифікат. Команди розраховано на Windows PowerShell 5.1. Усі скрипти, які вносять зміни, приймають `-WhatIf`.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$tls = Join-Path $env:SystemDrive 'project2-secrets\tls'
.\scripts\lan\New-Project2CA.ps1 -TlsDirectory $tls -ServerName foxlys.local
```

Підготуйте окремий каталог NTFS поза репозиторієм і сховищами даних. Доступ до нього мають власник, SYSTEM і локальні Administrators. CA діє 10 років і має критичне обмеження імен (Name Constraints): він може підписати лише `foxlys.local`, `localhost` і DN `CN=foxlys.local`, усі IP-адреси виключено. Навіть за викрадення ключа CA ним не підробити сторонні сайти на клієнтах. Якщо `Test-Project2Lan.ps1` або браузер на Windows не приймають такий ланцюжок, створіть CA повторно в порожньому каталозі з `-NoNameConstraints` і повідомте про це в журналі змін. Збережіть його зашифрований `project2-ca.pfx` та пароль окремо для перевипуску. Сервер читає `server.crt.pem` і `server.key.pem`. Сертифікат містить імена `foxlys.local` та `localhost` і призначення `serverAuth`. За можливості створіть пару від імені Windows-акаунта завдання. Якщо PKI адмініструє інший власник, надайте завданню власний захищений каталог із копіями лише двох серверних PEM і вкажіть його в `.env`.

3. Для Security 1.8 спершу видайте й встановіть сертифікати на всіх ПК за кроками 1–2 розділу «Сертифікати пристроїв (mTLS)». Лише тоді зупиніть попередній процес сервера. У чинному `.env` замініть значення нижче. Збережіть робочий `DATABASE_URL`, ключі MFA і підпису. Підставте фактичні шляхи до PEM. Для нестандартного `.env` скрипти створення/поновлення CA, Firewall та реєстрації завдання приймають `-EnvFile`.

```dotenv
PROJECT2_SERVER_NAME=foxlys.local
PROJECT2_BIND_HOST=0.0.0.0
PROJECT2_PORT=8443
PROJECT2_TLS_CERT=C:/project2-secrets/tls/server.crt.pem
PROJECT2_TLS_KEY=C:/project2-secrets/tls/server.key.pem
PROJECT2_ALLOWED_NETWORKS=auto
PROJECT2_CLIENT_CA=C:/project2-secrets/device-ca/device-ca.crt.pem
PROJECT2_CLIENT_CRL=C:/project2-secrets/device-ca/device-ca.crl.pem
PROJECT2_AUTH_ALLOW_LOCAL_HTTP=0
PROJECT2_WEBAUTHN_RP_ID=foxlys.local
PROJECT2_WEBAUTHN_ORIGINS=["https://foxlys.local:8443"]
```

`0.0.0.0` слухає активні IPv4-інтерфейси незалежно від адреси DHCP. Для розгортання через IPv6 задайте `PROJECT2_BIND_HOST=::` і перевірте доступність цього сімейства адрес на клієнтах. На порту 443 запишіть origin як `https://foxlys.local`. Особливості `auto` та явних CIDR описано в [SECURITY.md](SECURITY.md#security-17--lan).

4. Відкрийте Windows PowerShell як адміністратор. Звірте SHA-256 публічного CA з відбитком, отриманим під час створення, та встановіть довіру також на сервері. Далі налаштуйте правило вхідного TCP тільки для профілю Private і лише з локальної підмережі (`RemoteAddress LocalSubnet`). Скрипт повідомляє, чи увімкнено вхідне правило mDNS UDP 5353 для Private.

```powershell
$publicCA = Join-Path $env:SystemDrive 'project2-secrets\tls\project2-ca.cer'
.\scripts\lan\Install-Project2ClientCA.ps1 -CertificatePath $publicCA
.\scripts\lan\Set-Project2Firewall.ps1
```

5. Зареєструйте завдання для вибраного Windows-акаунта, який має право пакетного входу, доступ до коду, `.env`, ключа TLS та робочих каталогів. Пароль запитує `Get-Credential`. Для першої перевірки запустіть завдання одразу.

```powershell
$taskUser = Read-Host 'Введіть ДОМЕН\користувач або КОМПʼЮТЕР\користувач'
.\scripts\lan\Register-Project2Task.ps1 -UserName $taskUser
Start-ScheduledTask -TaskName 'Project2-LAN'
.\scripts\lan\Register-Project2Task.ps1 -Status
.\scripts\lan\Test-Project2Lan.ps1
```

Task Scheduler запускає `.venv\Scripts\python.exe -m app.serve` з кореня репозиторію при старті Windows, зокрема до інтерактивного входу. Після помилки передбачено три перезапуски з інтервалом одна хвилина. Паралельний запуск пропускається, час роботи необмежений. stdout/stderr за замовчуванням записуються у `%ProgramData%\Project2\LanLogs\server.log`. Після досягнення 5 MiB створюється наступний файл журналу, зберігаються три попередні. Для заміни шляху є `-LogDirectory`, для зняття реєстрації — `Register-Project2Task.ps1 -Unregister`. Для ручного запуску з тим самим `.env` виконайте `.\.venv\Scripts\python.exe -m app.serve` після зупинки завдання.

### На кожному клієнтському ПК

1. Передайте `project2-ca.cer`, `Install-Project2ClientCA.ps1`, `Test-Project2Lan.ps1` та їхній `Project2Lan.psm1`. Отримайте SHA-256 від адміністратора окремим довіреним каналом. У PowerShell адміністратора виконайте перші дві команди, звірте відбиток і підтвердьте установку. Діагностика працює під звичайним користувачем.

```powershell
$expected = Read-Host 'Контрольний SHA-256 CA'
.\Install-Project2ClientCA.ps1 -CertificatePath .\project2-ca.cer -ExpectedSha256 $expected
.\Test-Project2Lan.ps1
```

2. У версії 1.8 спочатку встановіть сертифікат пристрою для користувача браузера. Діагностика перевіряє системне розпізнавання імені, TCP, взаємний TLS, довіру до серверного сертифіката, HSTS і відповідь `HTTP 200` на `/auth/login`. Відкрийте `https://foxlys.local:8443/auth/login` та увійдіть із персональною MFA. Перевірте довіру в браузері, яким користуватиметься цей ПК. Браузер із власним сховищем CA потребує довіри до того самого публічного сертифіката у своїх налаштуваннях.

### Зміна мережі та перевипуск

Якщо нова довірена мережа має профіль Private і Windows mDNS розпізнає `foxlys.local`, сервер та клієнти продовжують використовувати ту саму адресу. `auto` оновлює активні підмережі при зверненнях з інтервалом щонайменше 60 с. Для мережі Public перевірте попередження `Set-Project2Firewall.ps1`. Переведіть інтерфейс у Private тільки після перевірки мережі.

Якщо mDNS недоступний, з’ясуйте поточну адресу сервера через `Get-NetIPAddress`. На відповідному клієнті відкрийте PowerShell адміністратора та виконайте команди нижче. Після зміни DHCP-адреси повторіть їх з новою адресою. `-Remove` видаляє позначений запис цього імені.

```powershell
$serverIP = Read-Host 'Поточна LAN-адреса сервера foxlys'
.\Add-Project2HostsEntry.ps1 -IPAddress $serverIP
.\Test-Project2Lan.ps1
```

Для резервного варіанту передайте клієнту також `Add-Project2HostsEntry.ps1`. Якщо ім’я вже записане в `hosts` іншим адміністратором, перевірте такий запис окремо. Скрипт керує лише рядком з `# project2`.

Серверна пара діє до 824 днів від дати випуску, у межах строку CA. За 30 днів до завершення виконайте `.\scripts\lan\Renew-Project2ServerCert.ps1 -TlsDirectory $tls`. Поза цим вікном свідомий перевипуск доступний через `-Force`. Введіть пароль PFX. Після успішної заміни обох PEM перезапустіть завдання та повторіть `Test-Project2Lan.ps1`. Якщо завдання читає окремі копії PEM, оновіть обидві перед перезапуском. За того самого CA довіра на клієнтах зберігається. Для заміни кореневого CA поширте новий публічний сертифікат і перевірте його відбиток на кожному ПК.

## Сертифікати пристроїв (mTLS)

Під час переходу з Security 1.7 залиште чинне завдання LAN запущеним до завершення кроків 1 і 2. Серверний CA та його довіра на клієнтах зберігаються. Для нового встановлення підготуйте серверну TLS-пару за розділом «Етап LAN» і виконайте ці самі кроки до першого запуску завдання.

1. **Підготуйте Device CA і видайте окремий PFX на кожен ПК, включно з `foxlys`.** На сервері відкрийте PowerShell у корені застосунку під Windows-акаунтом відповідального за CA. CLI читає чинний файл конфігурації для перевірки шляхів. Виберіть порожній приватний каталог NTFS поза репозиторієм і сховищами даних. Наведені команди обмежують доступ до нього власником, SYSTEM і локальними адміністраторами.

   ```powershell
   $ca = Join-Path $env:SystemDrive 'project2-secrets\device-ca'
   $python = '.\.venv\Scripts\python.exe'
   Import-Module .\scripts\lan\Project2Lan.psm1
   Set-Project2PrivateDirectory $ca @() $null
   & $python -m app.security.device_ca init --dir $ca
   ```

   Введіть і підтвердьте пароль CA завдовжки щонайменше 12 символів. Для кожного PFX задайте окремий пароль. Збережіть зашифрований ключ CA, його сертифікат, актуальні `devices.json` і CRL у захищеній резервній копії. Пароль CA зберігайте окремо. Нижче приклад для двох ПК. Повторіть видачу для всіх фактичних імен, використовуючи латинські малі літери, цифри та дефіс. Вкажіть захищений каталог видачі або розблокований зашифрований носій.

   ```powershell
   $transfer = Read-Host 'Наявний каталог для зашифрованих PFX'
   foreach ($pc in @('foxlys', 'pc-01')) {
       & $python -m app.security.device_ca issue --dir $ca --name $pc --out (Join-Path $transfer "$pc.pfx")
       if ($LASTEXITCODE -ne 0) { throw "Видача для $pc зупинилася." }
   }
   & $python -m app.security.device_ca list --dir $ca
   ```

2. **Встановіть сертифікат на кожному ПК і на сервері.** Передайте відповідний PFX флешкою, пароль і надрукований SHA-256 сертифіката — окремим довіреним каналом. Відкрийте PowerShell під тим Windows-користувачем, який працюватиме в браузері. Разом зі скриптами скопіюйте `Project2Lan.psm1`. Приклад запуску з каталогу скриптів:

   ```powershell
   $pfx = Read-Host 'Шлях до PFX цього ПК'
   $sha = Read-Host 'SHA-256 сертифіката, отриманий від адміністратора'
   .\Install-Project2DeviceCert.ps1 -PfxPath $pfx -ExpectedSha256 $sha
   ```

   Перевірте ім’я й відбиток. Після імпорту в `Cert:\CurrentUser\My` підтвердьте видалення PFX із флешки та приберіть його інші транспортні копії. Флешка має бути зашифрованою ще до перенесення. У локальному сховищі ключ має політику заборони експорту. Сам PFX із паролем дозволяє імпорт на іншому ПК до відкликання. Довіру до **серверного** CA налаштуйте на кожному ПК через `Install-Project2ClientCA.ps1`. Сертифікат Device CA використовується на сервері для перевірки клієнтів.

3. **Коли кожен ПК готовий, увімкніть нову версію LAN.** У чинному `.env` збережіть налаштування Security 1.7 та додайте два шляхи. Для іншого диска вкажіть фактичне розташування.

   ```dotenv
   PROJECT2_CLIENT_CA=C:/project2-secrets/device-ca/device-ca.crt.pem
   PROJECT2_CLIENT_CRL=C:/project2-secrets/device-ca/device-ca.crl.pem
   ```

   Окремому Windows-акаунту завдання надайте прохід через каталог та читання двох публічних файлів. У PowerShell власника каталогу виконайте команди нижче. Права на зашифрований приватний ключ і реєстр залишаються у відповідального за CA. У Windows CLI зберігає ACL цільового файла при заміні CRL.

   ```powershell
   $taskUser = Read-Host 'Windows-акаунт завдання Project2-LAN'
   icacls $ca /grant "${taskUser}:(X)"
   icacls (Join-Path $ca 'device-ca.crt.pem') /grant "${taskUser}:(R)"
   icacls (Join-Path $ca 'device-ca.crl.pem') /grant "${taskUser}:(R)"
   .\scripts\lan\Restart-Project2Task.ps1
   ```

   Для першого встановлення зареєструйте завдання за розділом «Етап LAN». Перезапуск потребує прав адміністратора. У журналі запуску звірте скорочений SHA-256 Device CA, дату чинності CRL у UTC та кількість відкликаних сертифікатів.

4. **Перевірте кожен ПК.** Під користувачем браузера запустіть `.\Test-Project2Lan.ps1`. Очікуйте успішний взаємний TLS, `HTTP 200` та HSTS. Відкрийте `https://foxlys.local:8443/auth/login`, при першому запиті браузера виберіть сертифікат цього пристрою та увійдіть із паролем і MFA. У Firefox перевірте `security.osclientcerts.autoload` в `about:config` і довіру до серверного CA у профілі. У сучасних версіях Firefox завантаження клієнтських сертифікатів Windows зазвичай ввімкнено.

**Відкликання і поновлення.** Для загубленого ПК відкличте сертифікат на сервері й перезапустіть завдання, щоб завантажити новий CRL і закрити попередні з’єднання. Доступ інших ПК зберігається.

```powershell
& $python -m app.security.device_ca revoke --dir $ca --name pc-01 --reason keyCompromise
if ($LASTEXITCODE -eq 0) { .\scripts\lan\Restart-Project2Task.ps1 }
```

Для планової заміни використовуйте `superseded`, для виведення з експлуатації — `cessationOfOperation`. Замість `--name` можна передати `--serial` з реєстру. Новому ПК видайте окремий PFX. Перед завершенням 730 днів перевипустіть сертифікат пристрою. Для повторного використання імені спочатку відкличте попередній сертифікат, потім видайте новий та імпортуйте його на ПК. Для локального видалення старого ключа використовуйте `Remove-Project2DeviceCert.ps1` під користувачем браузера. Виберіть лише старий відбиток у підтвердженні. Серверне відкликання застосовується після перезапуску.

Заплануйте щорічне поновлення CRL через `& $python -m app.security.device_ca crl --dir $ca` та `.\scripts\lan\Restart-Project2Task.ps1`. Строк CRL — 400 днів. Команда `list` показує дату, а запуск сервера в останні 30 днів додає попередження в журнал. Прострочений CRL блокує LAN.

**Аварійний доступ із сервера.** Зупиніть `Project2-LAN` через `Stop-ScheduledTask`. У приватному каталозі створіть тимчасову копію чинного `.env` з тими самими параметрами БД, сховищ і секретами. У копії видаліть рядки `PROJECT2_SERVER_NAME`, `PROJECT2_TLS_CERT`, `PROJECT2_TLS_KEY`, `PROJECT2_CLIENT_CA`, `PROJECT2_CLIENT_CRL` і задайте:

```dotenv
PROJECT2_BIND_HOST=127.0.0.1
PROJECT2_PORT=8000
PROJECT2_AUTH_ALLOW_LOCAL_HTTP=1
PROJECT2_WEBAUTHN_RP_ID=localhost
PROJECT2_WEBAUTHN_ORIGINS=["http://localhost:8000"]
```

У новій консолі без мережевих змінних, які перекривають цей файл, запустіть `.\.venv\Scripts\python.exe -m app.serve --env-file <шлях-до-копії>`. Відкрийте `http://localhost:8000/auth/login` на самому сервері. Для RP `localhost` підійдуть пароль із TOTP або резервним кодом. Виправте сертифікати чи CRL, зупиніть тимчасовий процес через Ctrl+C та запустіть `Restart-Project2Task.ps1` зі штатною LAN-конфігурацією. Після перевірки клієнта видаліть тимчасову копію конфігурації.

## Оновлення робочої версії

```powershell
cd C:\project2-prod
git pull origin main
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

Перед `upgrade` — свіжа перевірена резервна копія; сервер зупинений.
