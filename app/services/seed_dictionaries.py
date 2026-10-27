"""Programmatic acceptance of a validated package using the GUI's exact validators."""
from app.services.name_dictionary_import import read_workbook
from app.services.seed_packages import preflight_names
from app.repositories.seed_repository import name_rows


def seed_name_package(factory, directory, prepared=None):
    prepared=prepared or preflight_names(directory)
    values=[]; seen=set()
    for path in prepared['books']:
        rows,errors=read_workbook(path.read_bytes())
        if errors: raise ValueError(path.name+': '+'; '.join(errors))
        for row in rows:
            value=row['values']; key=(value['kind'],value['sex'],value['normalized_key'])
            if key in seen: raise ValueError(f'{path.name}, {row["sheet"]}, рядок {row["row"]}: дубль між книгами.')
            seen.add(key); values.append(value)
    # Accepted package means is_verified=True for lookup eligibility, not human academic review.
    with factory.begin() as db:
        return name_rows(db,values)
