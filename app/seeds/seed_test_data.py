from pathlib import Path
import json
from app.database.db_test import SessionLocal_test
from app.models.person import Person 

DATA_FILE_DIR = Path("app/seeds")
DATA_FILE = DATA_FILE_DIR /"data.json"

with open(DATA_FILE, "r", encoding="utf-8") as file:
    data = json.load(file)

for item in data:
    print(item)