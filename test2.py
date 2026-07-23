from pathlib import Path
import pandas as pd
import re

# ==========================
# ВКАЗАТИ СВОЇ ШЛЯХИ
# ==========================
excel_file = r"D:\Документи\Список.xlsx"
folders_path = r"D:\Документи\Папки"
# ==========================

sheet_name = "РБпСсп"
column = "H"


def get_excel_surname(text):
    """Повертає прізвище з ПІБ."""
    if pd.isna(text):
        return None
    text = str(text).strip()
    return text.split()[0].upper() if text else None


def get_folder_surname(folder_name):
    """Повертає прізвище з назви папки."""
    folder_name = folder_name.strip()

    match = re.search(r"Розшукова\s+картка\s+(.+)", folder_name, re.IGNORECASE)
    if match:
        rest = match.group(1).strip()
        return rest.split()[0].upper()

    return folder_name.split()[0].upper()


# Excel
df = pd.read_excel(
    excel_file,
    sheet_name=sheet_name,
    usecols=column,
    dtype=str
)

excel_surnames = {
    get_excel_surname(x)
    for x in df.iloc[:, 0]
    if get_excel_surname(x)
}

# Папки
folder_surnames = {
    get_folder_surname(folder.name)
    for folder in Path(folders_path).iterdir()
    if folder.is_dir()
}

missing = sorted(excel_surnames - folder_surnames)
extra = sorted(folder_surnames - excel_surnames)

result_file = Path(excel_file).parent / "result.txt"

with open(result_file, "w", encoding="utf-8") as f:
    f.write("=== Не вистачає ===\n\n")
    for surname in missing:
        f.write(surname + "\n")

    f.write("\n\n=== Зайві ===\n\n")
    for surname in extra:
        f.write(surname + "\n")

print("Готово!")
print(result_file)