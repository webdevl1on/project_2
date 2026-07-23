from pathlib import Path
import pandas as pd

# ==========================
# ВКАЗАТИ СВОЇ ШЛЯХИ
# ==========================
excel_file = r"C:\Users\LYS\Desktop\РБпССП_236_на_20.07.26 NEW.xlsx"
folders_path = r"C:\Users\LYS\Desktop\ASF\Документи"
# ==========================

sheet_name = "РБпСсп"
column = "H"

# Зчитування ПІБ з Excel
df = pd.read_excel(
    excel_file,
    sheet_name=sheet_name,
    usecols=column,
    dtype=str
)

excel_names = {
    str(name).strip()
    for name in df.iloc[:, 0]
    if pd.notna(name) and str(name).strip()
}

# Список папок
folder_names = {
    folder.name.strip()
    for folder in Path(folders_path).iterdir()
    if folder.is_dir()
}

# Порівняння
missing_folders = sorted(excel_names - folder_names)
extra_folders = sorted(folder_names - excel_names)

# Запис результату
result_file = Path(excel_file).parent / "result.txt"

with open(result_file, "w", encoding="utf-8") as f:
    f.write("=== Папок не вистачає ===\n\n")
    count = 1
    for name in missing_folders:
        f.write(str(count) + "." + name + "\n")
        count += 1
    count = 1
    f.write("\n\n=== Зайві папки ===\n\n")
    for name in extra_folders:
        f.write(str(count) + "." + name + "\n")
        count += 1

print(f"Готово! Результат збережено:\n{result_file}")