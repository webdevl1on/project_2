"""Unofficial attachments have no effect on official assignment queries."""
from app.models import PersonPositionMirage,Person,Position,StaffVersion
from app.services.staff_service import StaffService,checked,write_unit
from app.repositories.staff_repository import StaffRepository
from app.repositories.service_history_repository import ServiceHistoryRepository as Repo


def create(db,person_id,position_id,note=None):
    if len(note or '')>1000:raise ValueError('Примітка: максимум 1000 символів.')
    with write_unit(db):
        checked(db,Person,person_id);checked(db,Position,position_id)
        if Repo.waiting(db,person_id):raise ValueError('Людина вже має активний Міраж. Спочатку скасуйте або оформіть його.')
        record=Repo.add(db,PersonPositionMirage(person_id=person_id,staff_position_id=position_id,note=(note or '').strip() or None));db.flush();return record.id


def cancel(db,key,revision,reason):
    if not (reason or '').strip() or len(reason)>1000:raise ValueError('Вкажіть причину скасування до 1000 символів.')
    with write_unit(db):
        record=checked(db,PersonPositionMirage,key,revision)
        if record.status!='waiting':raise ValueError('Міраж уже завершено.')
        record.status='cancelled';record.cancel_reason=reason.strip();db.flush()


def preview(db,key,revision,on,orders=None):
    record=checked(db,PersonPositionMirage,key,revision)
    if record.status!='waiting':raise ValueError('Міраж уже завершено.')
    snapshot=StaffService.assignment_snapshot(db,record.staff_position_id,record.person_id,on,orders)
    if snapshot['target']:raise ValueError('Цільова посада вже офіційно зайнята; спочатку явно завершіть призначення або скасуйте Міраж.')
    return {'id':key,'revision':revision,'snapshot':snapshot}


def convert(db,expected,confirmed=False):
    if not confirmed:raise ValueError('Підтвердьте офіційне призначення та завершення попередньої посади, якщо воно потрібне.')
    from datetime import date
    with write_unit(db):
        record=checked(db,PersonPositionMirage,expected['id'],expected['revision'])
        if record.status!='waiting':raise ValueError('Міраж уже завершено.')
        snapshot=expected['snapshot'];on=date.fromisoformat(snapshot['on'])
        if snapshot['person_id']!=record.person_id or snapshot['position_id']!=record.staff_position_id:raise ValueError('Некоректне підтвердження Міражу.')
        StaffService._assign_locked(db,record.staff_position_id,record.person_id,on,snapshot,True)
        assignment=StaffRepository.person_assignment_at(db,record.person_id,on)
        record.status='converted';record.converted_assignment_id=assignment.id;db.flush()
