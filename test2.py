from pathlib import Path
import pandas as pd
import re

# ==========================
# ВКАЗАТИ СВОЇ ШЛЯХИ
# ==========================
excel_file = r"C:\Users\LYS\Desktop\РБпССП_236_на_24.07.26 NEW.xlsx"
documents_path = r"C:\Users\LYS\Desktop\Розібрати\Список особового складу РБпСсп"
# ==========================

sheet_name = "РБпСсп"
column = "H"

def normalize_person(text: str) -> str:
    text = text.upper()
    text = text.replace(".", "")
    text = " ".join(text.split())
    return text

def get_excel_person(text: str) -> str:
    """
    Яценко Сергій Олександрович
    ->
    ЯЦЕНКО С.О.
    """
    parts = str(text).strip().split()

    if len(parts) < 3:
        return str(text).strip().upper()

    surname = parts[0].upper()
    initials = f"{parts[1][0].upper()}.{parts[2][0].upper()}"

    return f"{surname} {initials}"


def get_document_person(file_name: str) -> str:
    """
    Перетворює різні варіанти назв документів у формат:
    ЯЦЕНКО С.О.

    Підтримує:
    Розшукова картка Яценко С.О.
    Розшукова картка Яценко С.О
    Розшукова картка Яценко С О
    Розшукова    картка     Яценко    С   О
    Яценко С.О.
    Яценко С О
    """

    # Прибираємо "Розшукова картка", якщо є
    file_name = re.sub(
        r"^\s*Розшукова\s+картка\s*",
        "",
        file_name,
        flags=re.IGNORECASE,
    ).strip()

    # Замінюємо всі крапки на пробіли
    file_name = file_name.replace(".", " ")

    # Прибираємо зайві пробіли
    parts = file_name.split()

    if len(parts) < 3:
        return file_name.upper()

    surname = parts[0].upper()
    initials = f"{parts[1][0].upper()}.{parts[2][0].upper()}."

    return f"{surname} {initials}"


# ---------- Excel ----------
df = pd.read_excel(
    excel_file,
    sheet_name=sheet_name,
    usecols=column,
    dtype=str
)

excel_persons = {
    normalize_person(get_excel_person(name))
    for name in df.iloc[:, 0]
    if pd.notna(name) and str(name).strip()
}

# ---------- Документи ----------

document_persons = {
    normalize_person(get_document_person(file.stem))
    for file in Path(documents_path).iterdir()
    if file.is_file() and file.suffix.lower() in (".doc", ".docx")
}


# ---------- Порівняння ----------
missing = sorted(excel_persons - document_persons)
extra = sorted(document_persons - excel_persons)

# ---------- Запис результату ----------
result_file = Path(excel_file).parent / "resultRK.txt"

with open(result_file, "w", encoding="utf-8") as f:
    f.write("=== Не вистачає документів ===\n\n")

    for person in missing:
        f.write(person + "\n")

    f.write("\n=== Зайві документи ===\n\n")

    for person in extra:
        f.write(person + "\n")

print("=" * 40)
print("Перевірку завершено.")
print(f"В Excel: {len(excel_persons)}")
print(f"Документів: {len(document_persons)}")
print(f"Не вистачає: {len(missing)}")
print(f"Зайвих: {len(extra)}")
print(f"Результат збережено:\n{result_file}")