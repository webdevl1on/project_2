"""Print fresh secrets for a new production .env.

Values are printed only to the console; nothing is written to disk.
Copy them into .env and into an offline backup before first start.
Usage (from repository root): python scripts/generate_production_secrets.py
"""
import json
import secrets

from cryptography.fernet import Fernet


def main():
    print('# --- Вставте у .env (не комітьте) та збережіть офлайн-копію ---')
    print(f'STAFF_SIGNING_KEY={secrets.token_urlsafe(48)}')
    print('PROJECT2_MFA_KEYS=' + json.dumps({'primary': Fernet.generate_key().decode()}))
    print('PROJECT2_MFA_CURRENT_KEY=primary')
    print(f'# Пароль ролі project2_prod (для \\password у psql та DATABASE_URL): {secrets.token_urlsafe(24)}')


if __name__ == '__main__':
    main()
