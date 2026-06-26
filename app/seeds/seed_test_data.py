from pathlib import Path
from app.utils.json_loader import load_json
from app.services.service_for_person import PersonService

DATA_FILE_DIR = Path("app/seeds")
DATA_FILE = DATA_FILE_DIR /"test_database_seed.json"

data =load_json(DATA_FILE)




for items in data[:2]:
    print(items["birth_date"])
        




