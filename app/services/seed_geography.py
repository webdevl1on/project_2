"""CSV adapter; bounded batches of Core rows, never 328k ORM objects."""
from itertools import islice
from app.repositories.seed_repository import geo_batch, city_batch, source_rows, alias_row
from app.services.seed_packages import TABLES, KINDS, PARENT_COLUMNS, FK_TABLES, csv_rows, preflight_geography


def seed_geography(engine, directory, prepared=None, *, batch_size=500, on_batch=None):
    prepared=prepared or preflight_geography(directory)
    mappings={}; report={}; sources=prepared['sources']; digest=prepared['digest']
    with engine.begin() as connection:
        source_rows(connection,sources)
        for table_name in TABLES:
            iterator=iter(csv_rows(directory,table_name)); count=0; created=0; mapped={}
            while batch:=list(islice(iterator,batch_size)):
                rows=[r[2] for r in batch]
                if table_name=='city_districts':
                    created+=city_batch(connection,rows,mappings['settlements'],sources,digest)
                elif table_name=='aliases':
                    # Source aliases never replace personal text snapshots.
                    for raw in rows:
                        target=raw['entity_type']; target=target if target in mappings else target+'s'
                        if target=='city_districts': raise ValueError('Alias внутрішньоміського району потребує окремого адаптера.')
                        unit_id=mappings[target][raw['entity_id']]
                        created+=alias_row(connection,unit_id,raw['alias'])
                else:
                    parents={}
                    for raw in rows:
                        for column in PARENT_COLUMNS.get(table_name,()):
                            if raw.get(column):
                                parents[raw['id']]=mappings[FK_TABLES[column]][raw[column]]; break
                    ids,added=geo_batch(connection,rows,KINDS[table_name],parents,sources,digest)
                    mapped.update(ids); created+=added
                count+=len(rows)
                if on_batch: on_batch(table_name,count)
            mappings[table_name]=mapped
            report[table_name]={'rows':count,'created':created,'existing':count-created}
    return report
