"""Fine-grained row locking only inside service-owned PostgreSQL writes."""
def locked_get(db,model,key):
    return db.get(model,key,populate_existing=True,with_for_update=True) if db.info.get('project2_write') and db.get_bind().dialect.name=='postgresql' else db.get(model,key)
