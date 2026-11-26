"""Allowlisted backup metadata for the web panel."""
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

KYIV = ZoneInfo('Europe/Kyiv')
ACTIVE_STATES = {'QUEUED', 'RUNNING'}
USB_VERSION = re.compile(r'\d{4}-\d{2}-\d{2}_\d{6}_([a-f0-9]{32})_usb_([a-f0-9]{32})')


def with_kyiv(data, *keys):
    for key in keys:
        value = data.get(key)
        data[f'{key}_kyiv'] = datetime.fromisoformat(value).astimezone(KYIV).strftime('%d.%m.%Y %H:%M') if value else None
    return data


def fields(record, *names):
    return {key: record[key] for key in names if key in record}


def public_job(job):
    data = with_kyiv(fields(job, 'id', 'at', 'operation', 'state', 'attempts', 'actor_user_id',
                            'backup_id', 'scheduled', 'completed_at'), 'at', 'completed_at')
    code = error_code(job.get('code'))
    if code:
        data['code'] = code
    if not job.get('scheduled') and not job.get('authorized_at'):
        data['authorization_expires_at'] = (datetime.fromisoformat(job['at']) + timedelta(minutes=5)).isoformat()
    return data


def error_code(code):
    if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', code):
        return code
    return 'BACKUP_JOB_FAILED' if code else None


def public_backup(record):
    if record is None:
        return None
    return with_kyiv(fields(record, 'id', 'snapshot_at', 'kind', 'schedule', 'size',
                            'integrity', 'drill', 'external'), 'snapshot_at')


def public_event(event):
    if event is None:
        return None
    data = with_kyiv(fields(event, 'id', 'at', 'operation', 'result', 'actor_user_id', 'backup_id'), 'at')
    code = error_code(event.get('code'))
    if code:
        data['code'] = code
    data['details'] = {key: value for key, value in fields(event.get('details', {}), 'files', 'size', 'restore_seconds').items()
                       if type(value) in (int, float)}
    return data


def public_statistics(record):
    if record is None:
        return None
    result = fields(record, 'at', 'database_size', 'growth_7_days', 'low_space', 'last_success', 'last_failure')
    for key in ('backups', 'excel', 'documents'):
        result[key] = fields(record[key], 'size', 'count', 'files', 'free')
    return with_kyiv(result, 'at', 'last_success', 'last_failure')


def public_emergency(record):
    if record is None:
        return None
    file_count = record['file_count'] if 'file_count' in record else len(record.get('files', ()))
    return with_kyiv({**fields(record, 'id', 'at', 'day'), 'file_count': file_count,
                      'size': sum(book['size'] for book in record['books'].values())}, 'at')


def volume_label(engine, job):
    volume_id = job.get('details', {}).get('volume_id')
    if not volume_id:
        return None
    from .windows_storage import cached_volumes
    try:
        volumes = cached_volumes(engine)
    except (ValueError, OSError, KeyError):
        return None
    label = next((volume.get('label') for volume in volumes if volume['id'] == volume_id), None)
    if not isinstance(label, str) or not re.fullmatch(r'[\w .()-]{1,32}', label):
        return None
    if re.search(r'S-1-\d+(-\d+)+', label, re.IGNORECASE) or re.search(r'[0-9a-f]{32,}|(?:[0-9a-f]{8}-){1}[0-9a-f-]{27}', label, re.IGNORECASE):
        return None
    return label.strip() or None


def last_usb(engine, jobs, events, versions, latest):
    # Job results survive journal pagination. A successful journal entry can also
    # survive an interruption between copying the files and finalizing the job.
    completed = [(datetime.fromisoformat(job['completed_at']), job['result'], job)
                 for job in jobs if job['operation'] == 'usb' and job['state'] == 'SUCCESS'
                 and job.get('completed_at') and isinstance(job.get('result'), dict)]
    event = next((event for event in reversed(events) if event['operation'] == 'usb' and event['result'] == 'SUCCESS'), None)
    if event:
        completed.append((datetime.fromisoformat(event['at']), event['details'], {}))
    if not completed:
        return None
    at, details, job = max(completed, key=lambda entry: entry[0])
    match = USB_VERSION.fullmatch(details.get('version') or '')
    excel = None
    if match:
        source_id, job_id = match.groups()
        excel = versions.get(source_id)
        if not job:
            job = next((row for row in jobs if row['id'] == job_id and row['operation'] == 'usb'), {})
    return with_kyiv({'at': at.isoformat(), 'label': volume_label(engine, job),
                      'excel_at': excel['at'] if excel else None,
                      'files': details.get('files') if type(details.get('files')) is int else None,
                      'outdated': bool(excel and latest and datetime.fromisoformat(excel['at']) < datetime.fromisoformat(latest['at']))},
                     'at', 'excel_at')
