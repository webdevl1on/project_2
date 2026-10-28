"""Additive service evolution, kept separate from prior migration contracts."""
ADDED_COLUMNS={
    'persons':{'personal_number'},
    'person_assignments':{'assignment_order_number','assignment_order_date','release_order_number','release_order_date','completion_reason','completion_note'},
    'person_service_history':{'end_day','end_month','end_year','end_date','note','revision'},
}


def install_order_guards(connection):
    checks=[]
    for field in ('assignment_order_date','release_order_date'):
        checks.append(f"(NEW.{field} IS NOT NULL AND (length(NEW.{field}) != 10 OR NEW.{field} < '0001-01-01' OR date(NEW.{field}, '+0 days') IS NULL OR date(NEW.{field}, '+0 days') != NEW.{field}))")
    for action in ('insert','update'):
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS exact_assignment_orders_{action} BEFORE {action.upper()} ON person_assignments WHEN {' OR '.join(checks)} BEGIN SELECT RAISE(ABORT,'exact order dates required'); END")
