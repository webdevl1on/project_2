"""Stable domain codes and UI metadata; no executable client definitions."""
FITNESS = {'FIT':'Придатний', 'FIT_SUPPORT':'Придатний до служби в тилових частинах забезпечення', 'UNFIT':'Непридатний'}
EXAM_STATES = {'NEEDS_EXAM':'Потребує проходження ВЛК', 'PLANNED':'Заплановано', 'COMPLETED':'ВЛК пройдено'}
BASES = {'INJURY':'Поранення', 'ILLNESS':'Захворювання', 'OTHER':'Інша причина'}
AWARD_STATES = {'NOT_PROCESSED':'Не опрацьовано', 'SUBMITTED':'Подано на нагородження', 'WAITING':'Очікує нагородження', 'AWARDED':'Нагороджено', 'NOT_APPROPRIATE':'Недоцільно нагороджувати'}
TASK_STATES = {'OPEN':'Відкрите', 'COMPLETED':'Завершене', 'CANCELLED':'Скасоване'}
DOCUMENT_ROLES = {
 'exams': {'certificate':'Довідка ВЛК', 'recommendation':'Рекомендація до ВЛК', 'discharge':'Виписка', 'other':'Інша підстава'},
 'injuries': {'form100':'Форма 100', 'combat_certificate':'Довідка про поранення в бою', 'circumstances':'Довідка про обставини травми', 'discharge':'Виписка з лікарні / медичної картки'},
 'awards': {'submission':'Подання', 'refusal_report':'Рапорт про недоцільність', 'award_order':'Наказ про нагородження', 'other':'Інший документ'},
}
# field, Ukrainian label, HTML type, maximum length / stable choices
FORM_FIELDS = {
 'exams': [('status','Стан','select',EXAM_STATES),('basis','Підстава','select',BASES),('basis_note','Опис підстави','text',2000),('injury_id','Поранення (необов’язково)','injury',None),('planned_on','Запланована дата','date',None),('issued_on','Дата видачі довідки','date',None),('number','Номер довідки','text',150),('institution','Установа ВЛК','text',1000),('diagnosis','Короткий діагноз','text',2000),('fitness','Придатність','select',FITNESS)],
 'injuries': [('occurred_on','Дата поранення','date',None),('description','Короткий опис','text',200),('area','Район поранення','text',1000),('circumstances','Обставини','text',2000),('certificate_number','Номер довідки','text',150),('certificate_on','Дата довідки','date',None),('exam_not_needed','ВЛК не потребує','checkbox',None)],
 'awards': [('name','Нагорода / питання нагородження','text',250),('status','Стан','select',AWARD_STATES),('injury_id','Пов’язане поранення','injury',None),('submission_on','Дата фактичного подання','date',None),('submission_number','Реквізити подання','text',150),('submission_confirmed','Підтверджую оформлення та фактичне подання','checkbox',None),('refusal_on','Дата рапорту про недоцільність','date',None),('refusal_number','Номер рапорту','text',150),('refusal_reason','Коротке обґрунтування','text',1000),('refusal_confirmed','Підтверджую оформлення рапорту','checkbox',None),('awarded_on','Дата нагородження','date',None),('order_number','Номер наказу','text',150),('order_on','Дата наказу','date',None)],
 'dna': [('envelope_number','Номер конверта','text',150),('collected_on','Дата здачі','date',None),('storage_unit','Військова частина зберігання','text',250)],
 'tasks': [('title','Завдання','text',250),('responsible','Відповідальні відомості','text',500),('note','Примітка','text',2000),('injury_id','Пов’язане поранення','injury',None),('award_id','ID пов’язаного нагородження','number',None),('status','Стан','select',TASK_STATES),('decision_reason','Причина ручного завершення / скасування','text',1000)],
}
LABELS = {'exams':'ВЛК','injuries':'Поранення','awards':'Нагородження','dna':'ДНК','tasks':'Проблемні питання / Завдання'}
