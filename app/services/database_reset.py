"""Build, verify, back up, then atomically publish a test SQLite database."""
from datetime import datetime, UTC
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile
import uuid
from app.database.maintenance import database_lease

SUFFIXES=('-wal','-shm','-journal')


def check_target(path):
    path=Path(path)
    if any(Path(str(path)+suffix).exists() for suffix in SUFFIXES):
        raise ValueError('Є WAL/SHM/journal-файли. Зупиніть сервер і коректно закрийте підключення; заміну заборонено.')
    if path.is_symlink(): raise ValueError('Ціль БД не може бути символічним посиланням.')
    if path.exists():
        if not path.is_file(): raise ValueError('Ціль БД не є звичайним файлом.')
        with path.open('rb') as stream:
            if stream.read(16)!=b'SQLite format 3\x00': raise ValueError('Наявна ціль не є SQLite; заміну заборонено.')
        # Detect even idle SQLite handles on Linux, not only active transactions.
        proc=Path('/proc')
        if proc.is_dir():
            for process in proc.iterdir():
                if not process.name.isdecimal() or int(process.name)==os.getpid(): continue
                try:
                    for descriptor in (process/'fd').iterdir():
                        try:
                            if descriptor.resolve()==path.resolve(): raise ValueError('Інший процес тримає відкриту SQLite; заміну заборонено.')
                        except (FileNotFoundError,PermissionError): pass
                except (FileNotFoundError,PermissionError): pass


def check_space(path, required):
    parent=Path(path).parent
    while not parent.exists(): parent=parent.parent
    if not os.access(parent,os.W_OK): raise ValueError('Каталог БД недоступний для запису.')
    if shutil.disk_usage(parent).free < required: raise ValueError('Недостатньо вільного місця для staging, БД і backup.')


def publish(staging,target):
    target=Path(target); check_target(target)
    backup=None
    original=None
    try:
        if target.exists():
            # Locks from unknown SQLite clients also prevent replacement.
            original=sqlite3.connect(target.as_uri()+'?mode=rw',uri=True,timeout=0)
            original.execute('BEGIN EXCLUSIVE'); original.rollback()
            stamp=datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
            backup=target.with_name(f'{target.stem}.before-reset-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3')
            descriptor=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.close(descriptor)
            with sqlite3.connect(backup) as copied: original.backup(copied)
            original.close(); original=None
        check_target(target)
        # Same directory/filesystem: replacement is atomic; failure retains the old target.
        with Path(staging).open('r+b') as stream: os.fsync(stream.fileno())
        os.replace(staging,target)
        return backup
    finally:
        if original is not None: original.close()


def reset_database(target, build, *, required_space=0):
    target=Path(target).absolute()
    check_target(target); check_space(target,required_space)
    target.parent.mkdir(parents=True,exist_ok=True)
    with database_lease(target):
        check_target(target)
        descriptor, filename=tempfile.mkstemp(prefix='.'+target.stem+'.staging-',suffix='.sqlite3',dir=target.parent)
        os.close(descriptor); staging=Path(filename)
        try:
            report=build(staging)
            backup=publish(staging,target)
            return report,backup
        finally:
            # Only paths created by this invocation are ever removed.
            staging.unlink(missing_ok=True)
            for suffix in SUFFIXES: Path(str(staging)+suffix).unlink(missing_ok=True)
