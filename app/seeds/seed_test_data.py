from pathlib import Path
from app.database.db_test import SessionLocal_test
from app.database.db import SessionLocal
from app.utils.json_loader import load_json
from app.services.service_for_person import PersonService

DATA_FILE_DIR = Path("app/seeds")
DATA_FILE = DATA_FILE_DIR /"test_database_seed.json"

data =load_json(DATA_FILE)
db =SessionLocal()


def new_1(data):
    result=[]
    for person_dict in data[:3]:
        result.append( PersonService.create_person(person_dict['pib'],
        person_dict['rank'],
        person_dict['birth_date'],
        person_dict['position'],
        person_dict['phone'],
        person_dict['status']))
    return(result)

new_data = new_1(data)
for person in new_data:
    db.add(person)
db.commit()
db.close()