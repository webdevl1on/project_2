"""Stable account codes; neither username nor display_name grants privileges."""
ROLES = {'master':'Master','admin':'Admin','editor':'Редактор','viewer':'Спостерігач'}
ASSIGNABLE_ROLES = {key:value for key,value in ROLES.items() if key!='master'}
OPERATIONS = {'create':'Створення','edit':'Редагування','role_change':'Зміна ролі',
              'block':'Вимкнення','unblock':'Увімкнення','password_reset':'Скидання пароля',
              'password_change':'Зміна власного пароля','sessions_revoke':'Завершення сесій',
              'promote_master':'Початкове призначення Master'}


def personal(user):
    return bool(user and user.password_hash.startswith('scrypt$'))


def has_role(user, roles):
    return bool(user and (user.role in roles or user.role=='master' and 'admin' in roles))

OPERATIONS.update({'mfa_enroll':'Налаштування MFA','factor_add':'Додавання / перейменування фактора','factor_remove':'Видалення фактора','backup_use':'Використання резервного коду','backup_generate':'Нові резервні коди','mfa_recover':'Відновлення MFA','mfa_reauth':'Повторне підтвердження MFA'})
