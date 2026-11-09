"""PostgreSQL snapshot/recovery IO, with no HTTP or application authorization."""
from contextlib import contextmanager
from pathlib import Path
import os,re,subprocess,tempfile
from sqlalchemy import text
from app.services.backups.crypto import private_file
SSL_OPTIONS={'sslmode':'PGSSLMODE','sslrootcert':'PGSSLROOTCERT','sslcert':'PGSSLCERT','sslkey':'PGSSLKEY'}

class BackupRepository:
    @staticmethod
    def source(connection):
        if connection.dialect.name!='postgresql':raise ValueError('BACKUP_REQUIRES_POSTGRESQL')
        major=int(connection.scalar(text('SHOW server_version_num')))//10000
        if major!=17:raise ValueError('BACKUP_POSTGRESQL_17_REQUIRED')
        schema=connection.scalar(text('SELECT current_schema()'))
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',schema):raise ValueError('BACKUP_SCHEMA_INVALID')
        return schema
    @staticmethod
    def references(connection):return [dict(r) for r in connection.execute(text('SELECT storage_key,size,sha256 FROM document_files ORDER BY storage_key')).mappings()]
    @staticmethod
    def counts(connection):
        tables=connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() ORDER BY tablename"))
        return {name:connection.scalar(text('SELECT count(*) FROM "'+name.replace('"','""')+'"')) for name in tables}
    @staticmethod
    @contextmanager
    def lock(engine):
        with engine.connect() as connection:
            BackupRepository.source(connection)
            if not connection.scalar(text("SELECT pg_try_advisory_lock(hashtext(current_schema()),hashtext('project2_backup_job'))")):raise ValueError('BACKUP_ALREADY_RUNNING')
            try:yield connection
            finally:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(hashtext(current_schema()),hashtext('project2_backup_job'))"));connection.commit()
    @staticmethod
    @contextmanager
    def freeze(connection):
        connection.execute(text("SET lock_timeout='30s'"))
        connection.execute(text("SELECT pg_advisory_lock(hashtext(current_schema()),hashtext('project2_backup_snapshot'))"))
        try:yield
        finally:
            connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(hashtext(current_schema()),hashtext('project2_backup_snapshot'))"));connection.commit()
    @staticmethod
    @contextmanager
    def client(url,staging,schema=None):
        if url.drivername!='postgresql+psycopg' or not url.host or not url.username:raise ValueError('BACKUP_CONNECTION_INVALID')
        if set(url.query)-SSL_OPTIONS.keys() or any(not isinstance(v,str) for v in url.query.values()):raise ValueError('BACKUP_CONNECTION_OPTIONS_UNSUPPORTED')
        path=staging/'pgpass'
        def escape(v):return str(v).replace('\\','\\\\').replace(':','\\:')
        try:
            if any('\n' in str(v) or '\r' in str(v) for v in (url.host,url.database,url.username,url.password or '')):raise ValueError('BACKUP_CONNECTION_INVALID')
            with private_file(path) as out:out.write((':'.join(escape(v) for v in [url.host,url.port or 5432,url.database,url.username,url.password or ''])+'\n').encode())
            environment={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL','SSL_CERT_FILE')}
            environment.update(PGHOST=url.host,PGPORT=str(url.port or 5432),PGDATABASE=url.database,PGUSER=url.username,PGPASSFILE=str(path),PGCONNECT_TIMEOUT='10',PGOPTIONS='-c timezone=UTC -c statement_timeout=0'+(' -c search_path='+schema+',public' if schema else ''))
            environment.update({SSL_OPTIONS[k]:v for k,v in url.query.items()})
            yield environment
        finally:path.unlink(missing_ok=True)
    @staticmethod
    def tool(config,name,args,env,*,output=None):
        command=str(Path(config.tool_dir)/name) if config.tool_dir else name
        try:
            version=subprocess.run([command,'--version'],env=env,capture_output=True,timeout=10,check=True)
            if not re.search(rb'\b17\.',version.stdout):raise ValueError('BACKUP_CLIENT_VERSION_INVALID')
            result=subprocess.run([command,*args],env=env,stdout=output or subprocess.PIPE,stderr=subprocess.PIPE,timeout=4*3600)
            if result.returncode:raise ValueError('BACKUP_DATABASE_TOOL_FAILED')
        except (OSError,subprocess.SubprocessError):raise ValueError('BACKUP_DATABASE_TOOL_FAILED') from None
    @staticmethod
    def user(db,key):
        from app.models import User
        return db.get(User,key)
