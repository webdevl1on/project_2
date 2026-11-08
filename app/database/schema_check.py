"""Read-only check: create_all cannot upgrade an existing SQLite schema."""

from sqlalchemy import inspect

from app.database.base import Base


def required_sqlite_triggers():
    required = {f"guard_{table}_{action}" for table in ("staff_versions", "person_assignments")
                for action in ("insert", "update", "delete")}
    required.update(("guard_position_version", "guard_position_delete"))
    required.update(f"exact_{table}_{action}" for table in ("staff_versions", "person_assignments", "person_events")
                    for action in ("insert", "update"))
    return required


def require_current_schema(engine):
    from app import models  # Register all current tables before inspection.

    if engine.dialect.name=='postgresql':
        from app.database.postgresql import require_postgresql_schema
        require_postgresql_schema(engine)
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            missing.append(table.name)
            continue
        columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing.extend(f"{table.name}.{column.name}" for column in table.columns if column.name not in columns)
    if "person_positions" in tables:
        missing.append("застаріла фізична person_positions — підготуйте нову БД без другого джерела призначень")
    if engine.dialect.name == "sqlite" and not missing:
        from sqlalchemy import text
        required = required_sqlite_triggers() | {'account_audit_no_update','account_audit_no_delete','users_no_delete','users_no_insert_master','users_policy_update', "assignment_audit_no_update", "assignment_audit_no_delete", "assignment_annulled_guard", "exact_assignment_orders_insert","exact_assignment_orders_update", 'exact_service_basis_insert', 'exact_service_basis_update'}
        from app.models.documents import GUARD_NAMES
        required |= GUARD_NAMES
        from app.models.medical import GUARDS
        required |= GUARDS
        required |= {'access_audit_no_update','access_audit_no_delete'} | {table+'_no_delete' for table in ('access_rules','access_templates','access_template_assignments','position_access_policies','temporary_access','access_delegations','access_reviews')}
        with engine.connect() as connection:
            installed=set(connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'")).scalars())
        missing.extend("trigger:"+name for name in sorted(required-installed))
    if 'personnel_tasks' in tables and 'one_injury_vlk_task' not in {i['name'] for i in inspector.get_indexes('personnel_tasks')}:
        missing.append('index:one_injury_vlk_task')
    if 'personnel_tasks' in tables and 'exam_id' in {c['name'] for c in inspector.get_columns('personnel_tasks')} and 'one_exam_control_task' not in {i['name'] for i in inspector.get_indexes('personnel_tasks')}:missing.append('index:one_exam_control_task')
    if 'document_files' in tables and 'document_file_order' not in {i['name'] for i in inspector.get_indexes('document_files')}:
        missing.append('index:document_file_order')
    if missing:
        if set(missing)<={'document_files.sort_order','index:document_file_order'}:
            raise ValueError('Потрібна міграція: python -m app.database.migrate_document_file_order --database PATH. Автоматично БД не змінено.')
        from app.models.profile_records import NEW_TABLE_NAMES as PROFILE_TABLES
        if set(missing) <= PROFILE_TABLES:
            raise ValueError('Потрібна безпечна міграція: python -m app.database.migrate_profile_records --database PATH. Автоматично БД не змінено.')
        from app.database.migrate_vlk_workflow import ADDED
        workflow={t+'.'+c for t,cols in ADDED.items() for c in cols}|{'index:one_exam_control_task','trigger:medical_exam_no_new_interrupted','trigger:medical_exam_interrupted_history'}
        if set(missing)<=workflow:
            raise ValueError('Потрібна міграція ВЛК: python -m app.database.migrate_vlk_workflow --database PATH. Автоматично БД не змінено.')
        if set(missing)=={'index:one_injury_vlk_task'}:
            raise ValueError('Потрібна адитивна міграція: python -m app.database.migrate_injury_vlk --database PATH. Автоматично БД не змінено.')
        from app.models.medical import NEW_TABLE_NAMES as MEDICAL_TABLES, GUARDS
        if set(missing) <= MEDICAL_TABLES | {"trigger:"+name for name in GUARDS}:
            raise ValueError("Потрібна безпечна міграція: python -m app.database.migrate_medical --database PATH. Автоматично БД не змінено.")
        from app.models.documents import NEW_TABLE_NAMES as DOCUMENT_TABLES, GUARD_NAMES
        if set(missing) <= DOCUMENT_TABLES | {'trigger:'+name for name in GUARD_NAMES}:
            raise ValueError('Потрібна безпечна міграція: python -m app.database.migrate_documents --database PATH. Автоматично БД не змінено.')
        from app.models.service_basis import NEW_TABLE_NAMES
        if set(missing) <= NEW_TABLE_NAMES | {'trigger:exact_service_basis_insert', 'trigger:exact_service_basis_update'}:
            raise ValueError('Потрібна безпечна міграція: python -m app.database.migrate_service_bases --database PATH. Автоматично БД не змінено.')
        from app.database.service_schema import ADDED_COLUMNS
        changes={f'{table}.{name}' for table,names in ADDED_COLUMNS.items() for name in names}|{'person_position_mirages','trigger:exact_assignment_orders_insert','trigger:exact_assignment_orders_update'}
        if set(missing)<=changes:
            raise ValueError('Потрібна безпечна міграція: python -m app.database.migrate_service_history --database PATH. Автоматично БД не змінено.')
        if set(missing) == {"person_contacts"}:
            raise ValueError("Потрібна безпечна міграція: python -m app.database.migrate_contacts --database PATH. Автоматично БД не змінено.")
        if set(missing) <= {"geo_units", "geo_aliases", "person_birthplaces", "person_addresses"}:
            raise ValueError("Потрібна безпечна міграція: python -m app.database.migrate_geography --database PATH. Автоматично БД не змінено.")
        name_changes = {"persons.sex", "name_dictionaries", "person_name_cases", "name_dictionary_imports"}
        if set(missing) <= name_changes:
            raise ValueError("Потрібна безпечна міграція зі збереженням даних: python -m app.database.migrate_name_cases --database PATH. Автоматично БД не змінено.")
        raise ValueError("Схема SQLite застаріла або неповна. Відсутні: " + ", ".join(missing)
                         + ". Підготуйте нову базу або явно пересоздайте тестову; автоматичного оновлення немає.")
