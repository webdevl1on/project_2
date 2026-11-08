"""Read organizational staffing paths without database lookup or side effects.

The established positions attributes and explanatory second row remain intact.
Only the caller-selected root is accepted; names never select a global unit.
"""
from collections import defaultdict
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile
from unicodedata import normalize

from openpyxl import Workbook, load_workbook

from app.validators.position_validator import POSITION_ATTRIBUTES, validate_position

MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
_CHILD = re.compile(r"child_([1-9][0-9]{0,4})\Z")


def _name_key(value):
    # Deliberately identical to organization.normalize, without importing ORM code.
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError("Назва підрозділу: текст від 1 до 500 символів.")
    return " ".join(normalize('NFC', value).split()).casefold()


def _content(source):
    if isinstance(source, (bytes, bytearray)):
        content = bytes(source)
    else:
        try:
            if hasattr(source, "read"):
                source.seek(0)
                content = source.read(MAX_INPUT_BYTES + 1)
            else:
                with Path(source).open("rb") as stream:
                    content = stream.read(MAX_INPUT_BYTES + 1)
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("Не вдалося прочитати файл .xlsx.") from error
    if not isinstance(content, bytes):
        raise ValueError("Потрібен двійковий файл .xlsx.")
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError("Файл перевищує 5 МБ.")
    return content


def _headers(sheet):
    header = [str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
              for value in next(sheet.iter_rows(values_only=True), ())]
    while header and not header[-1]:
        header.pop()
    if not header or any(not name for name in header):
        raise ValueError("Порожня системна назва колонки Excel.")
    if len(header) != len(set(header)):
        raise ValueError("Повторні назви колонок Excel.")
    missing = {"parent", *POSITION_ATTRIBUTES} - set(header)
    if missing:
        raise ValueError("Відсутні колонки: " + ", ".join(sorted(missing)))
    children = []
    for name in header:
        if name in POSITION_ATTRIBUTES or name == "parent":
            continue
        match = _CHILD.fullmatch(name)
        if not match:
            raise ValueError(f"Невідома або некоректна колонка: {name}.")
        children.append(int(match.group(1)))
    if sorted(children) != list(range(1, len(children) + 1)):
        raise ValueError("Колонки child_N мають іти без пропусків: child_1, child_2, …")
    return header, ["parent", *[f"child_{number}" for number in sorted(children)]]


def _path(record, path_columns):
    values = [record.get(name) for name in path_columns]
    while len(values) > 1 and (values[-1] is None or str(values[-1]).strip() == ""):
        values.pop()
    path, keys, errors = [], [], []
    for index, value in enumerate(values):
        if value is None or (isinstance(value, str) and not value.strip()):
            path.append("")
            keys.append("")
            errors.append("Колонка parent обов’язкова." if index == 0 else
                          f"Пропуск у шляху підпорядкування: {path_columns[index]}.")
            continue
        path.append(value.strip() if isinstance(value, str) else str(value))
        try:
            keys.append(_name_key(value))
        except ValueError as error:
            keys.append("")
            errors.append(f"{path_columns[index]}: {error}")
    return path, keys, errors


def read_positions(source, root_name):
    """Return row candidates and conflicts; malformed workbooks raise ValueError.

    Each candidate includes physical ``row_number``, original ``path``, normalized
    ``path_keys``, validated ``position`` and its own ``errors``. Bad paths and
    conflicting position numbers remain in the result for a manual preview.
    Identical repetitions are retained with ``duplicate_of`` and a warning.
    """
    selected_key = _name_key(root_name)
    content = _content(source)
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise ValueError("Розпакований Excel перевищує 50 МБ.")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("Не вдалося прочитати файл .xlsx.") from error
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as error:
        raise ValueError("Не вдалося прочитати файл .xlsx.") from error
    rows, errors, warnings = [], [], []
    try:
        if "positions" not in book.sheetnames:
            raise ValueError("Аркуш positions відсутній.")
        sheet = book["positions"]
        header, path_columns = _headers(sheet)
        for row_number, values in enumerate(sheet.iter_rows(min_row=3, values_only=True), 3):
            if not any(value is not None and str(value).strip() for value in values):
                continue
            record = dict(zip(header, values))
            position_errors=[]
            try:
                number = record.get("position_number")
                if isinstance(number, bool) or (isinstance(number, float) and not number.is_integer()):
                    raise ValueError("Номер посади має бути цілим числом.")
                position = validate_position(record)
            except (ValueError, TypeError, KeyError) as error:
                position_errors.append(str(error))
                position={key:value if value is None or isinstance(value,(str,int,float,bool)) else str(value)
                          for key in POSITION_ATTRIBUTES for value in [record.get(key)]}
            path, keys, row_errors = _path(record, path_columns)
            row_errors.extend(position_errors)
            if keys[0] and keys[0] != selected_key:
                row_errors.append("parent не відповідає вибраному підрозділу; потрібне ручне рішення.")
            if any(value is not None and str(value).strip() for value in values[len(header):]):
                row_errors.append("Дані в колонці без системного заголовка.")
            rows.append({"row_number": row_number, "path": path, "path_keys": keys,
                         "position": position, "position_valid":not position_errors, "errors": row_errors})
    finally:
        book.close()
    by_number = defaultdict(list)
    for row in rows:
        if row['position_valid']:by_number[row["position"]["position_number"]].append(row)
    for number, group in by_number.items():
        if len(group) < 2:
            continue
        signatures = {(tuple(row["path_keys"]), tuple(row["position"].items())) for row in group}
        if len(signatures) > 1:
            references = ", ".join(str(row["row_number"]) for row in group)
            message = f"Конфлікт номера посади {number}: різні реквізити або шляхи в рядках {references}."
            for row in group:
                row["errors"].append(message)
        else:
            first = group[0]["row_number"]
            for row in group[1:]:
                row["duplicate_of"] = first
                warnings.append(f"Рядок {row['row_number']}: точний повтор рядка {first}; не створюйте другу посаду.")
    errors.extend(f"Рядок {row['row_number']}: {message}" for row in rows for message in row["errors"])
    if not any(row['position_valid'] for row in rows):
        errors.append("Немає коректних посад для імпорту.")
    return {"rows": rows, "errors": errors, "warnings": warnings}


def empty_template(depth=3):
    """Return the established workbook with arbitrary contiguous child_N slots."""
    if type(depth) is not int or not 0 <= depth <= 16384 - len(POSITION_ATTRIBUTES) - 1:
        raise ValueError("Глибина шаблону має бути невід’ємним цілим числом у межах Excel.")
    book = Workbook()
    sheet = book.active
    sheet.title = "positions"
    columns = ["parent", *[f"child_{number}" for number in range(1, depth + 1)], *POSITION_ATTRIBUTES]
    sheet.append(columns)
    labels = {"parent": "Вибраний кореневий підрозділ", "position_number": "Номер посади",
              "code": "Код", "unit_short": "Коротка назва підрозділу", "name_short": "Коротка назва посади",
              "name_nominative": "Називний", "name_genitive": "Родовий", "name_dative": "Давальний",
              "name_accusative": "Знахідний", "name_instrumental": "Орудний", "name_locative": "Місцевий",
              "name_vocative": "Кличний"}
    sheet.append([labels.get(column, f"Дочірній підрозділ {column.split('_')[-1]}") for column in columns])
    sheet.freeze_panes = "A3"
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()
