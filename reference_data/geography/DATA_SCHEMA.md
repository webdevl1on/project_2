# Схема даних для SQLAlchemy та SQLite

Усі CSV UTF-8 BOM, роздільник `;`, один рядок ключів. Excel має два рядки заголовків. Порожні клітинки імпортуються як NULL. ID/коди ніколи не перетворювати на числа.

## countries

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `name_uk` | Text | NOT NULL | Українська коротка назва з Переліку кодів країн |
| `iso_alpha2` | String(2) | UNIQUE, NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `iso_alpha3` | String(3) | UNIQUE, nullable | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `iso_numeric` | String(3) | text | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |

## regions

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `name` | Text | NOT NULL | Назва з джерела без крайових пробілів |
| `region_type` | Text | NOT NULL | oblast / autonomous_republic / special_city |
| `katottg_code` | String(19) | UNIQUE, NOT NULL | Повний код з КАТОТТГ |
| `country_id` | String(36) | FK countries.id; NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `country_code` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |

## districts

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `name` | Text | NOT NULL | Назва з джерела без крайових пробілів |
| `katottg_code` | String(19) | UNIQUE, NOT NULL | Повний код з КАТОТТГ |
| `region_id` | String(36) | FK regions.id; NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |

## communities

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `name` | Text | NOT NULL | Назва з джерела без крайових пробілів |
| `katottg_code` | String(19) | UNIQUE, NOT NULL | Повний код з КАТОТТГ |
| `region_id` | String(36) | FK regions.id; NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `district_id` | String(36) | FK districts.id; nullable | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |

## settlements

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `name` | Text | NOT NULL | Назва з джерела без крайових пробілів |
| `settlement_type` | Text | NOT NULL | city / village / settlement / special_city |
| `source_category` | Text | NOT NULL | Офіційна категорія M/C/X/K |
| `katottg_code` | String(19) | UNIQUE, NOT NULL | Повний код з КАТОТТГ |
| `region_id` | String(36) | FK regions.id; NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `district_id` | String(36) | FK districts.id; nullable | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `community_id` | String(36) | FK communities.id; nullable | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |

## city_districts

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `name` | Text | NOT NULL | Назва з джерела без крайових пробілів |
| `katottg_code` | String(19) | UNIQUE, NOT NULL | Повний код з КАТОТТГ |
| `region_id` | String(36) | FK regions.id; NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `settlement_id` | String(36) | FK settlements.id; NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |

## aliases

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `entity_type` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `entity_id` | String(36) | Типізований зв’язок; перевірка сервісом | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `alias` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `alias_kind` | Text | NOT NULL | previous_snapshot_name; це спостереження, не дата юридичного перейменування |
| `first_observed` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `last_observed` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `current_observed` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `valid_from` | Text | nullable | Юридична дата початку: NULL без доказу |
| `valid_to` | Text | nullable | Юридична дата завершення: NULL без доказу |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |

## streets

| Колонка | SQLAlchemy / SQL | Ключ / обмеження | Призначення |
|---|---|---|---|
| `id` | String(36) | PK, NOT NULL | Внутрішній UUID, не офіційний код |
| `name` | Text | NOT NULL | Назва з джерела без крайових пробілів |
| `street_type` | Text | nullable | Тип лише за розпізнаним префіксом; інакше NULL |
| `settlement_id` | String(36) | FK settlements.id; NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `external_code` | Text | nullable | Порожній: у завантаженому XML НАІС кодів вулиць немає |
| `link_method` | Text | NOT NULL | Метод однозначного зіставлення |
| `source_id` | String | FK geo_sources.id, NOT NULL | Версія джерела у sources.json |
| `source_row` | String | NOT NULL | Номер рядка XLSX, RECORD XML або сторінки PDF |
| `source_region` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_district` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_settlement` | Text | NOT NULL | Див. назву колонки та TECHNICAL_SPEC_UK.md |
| `source_city_district` | Text | NOT NULL | Незмінений контекст НАІС; не є FK на city_districts |
| `full_name` | Text | NOT NULL | Повна назва вулиці як у НАІС, включно з типом |

## Додаткова таблиця geo_sources

`id` String PK; `version_date` Date nullable (дата заявленої версії); `retrieved_date` Date NOT NULL; `url` Text NOT NULL; `sha256` String(64) NOT NULL; `license` Text; `local_file` Text. sources.json є машинозчитуваним реєстром. Дати у джерел не завжди означають дату фактичного останнього оновлення кожного запису.
