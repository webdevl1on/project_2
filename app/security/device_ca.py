"""Local Device CA administration. Run python -m app.security.device_ca --help."""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import warnings

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.database.maintenance import database_lease
from app.database.settings import Settings
from app.security.device_tls import PEM, single_pem
from app.security.network import external_path, protected_paths

KEY = 'device-ca.key.pem'
CERT = 'device-ca.crt.pem'
CRL = 'device-ca.crl.pem'
REGISTRY = 'devices.json'
REASONS = {'keyCompromise': x509.ReasonFlags.key_compromise, 'superseded': x509.ReasonFlags.superseded,
           'cessationOfOperation': x509.ReasonFlags.cessation_of_operation}
SHA256 = hashes.SHA256()


def prompt_password(label, *, confirm=False, minimum=1):
    # getpass normally falls back to echoed stdin if no terminal is available.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        value = getpass.getpass(label)
        if len(value) < minimum:
            raise ValueError(f'Мінімальна довжина пароля — {minimum}.')
        if confirm:
            if value != getpass.getpass('Повторіть пароль: '):
                raise ValueError('Введені паролі відрізняються.')
    return value.encode('utf-8')


@contextmanager
def staged(path, data):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '-')
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        yield temp
    finally:
        temp.unlink(missing_ok=True)


def replace_file(path, data):
    with staged(path, data) as temp:
        if os.name != 'nt' or not path.exists():
            os.replace(temp, path)
            return
        # The service account can have a read ACE on just the public CRL. ReplaceFileW
        # preserves the destination DACL when publishing a freshly signed list.
        import ctypes
        from ctypes import wintypes
        replace = ctypes.WinDLL('kernel32', use_last_error=True).ReplaceFileW
        replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                            wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
        replace.restype = wintypes.BOOL
        if not replace(str(path), str(temp), None, 0, None, None):
            raise ctypes.WinError(ctypes.get_last_error())


def publish_new(temp, path):
    # Windows rename refuses to overwrite; this also works on removable FAT/exFAT.
    if os.name == 'nt':
        os.rename(temp, path)
    else:
        os.link(temp, path)


def save_registry(directory, records):
    data = json.dumps(records, ensure_ascii=False, indent=2) + '\n'
    replace_file(directory / REGISTRY, data.encode('utf-8'))


def key_usage(ca):
    return x509.KeyUsage(digital_signature=not ca, content_commitment=False, key_encipherment=False,
                         data_encipherment=False, key_agreement=False, key_cert_sign=ca, crl_sign=ca,
                         encipher_only=False, decipher_only=False)


def build_crl(ca, key, number, revoked, now):
    builder = (x509.CertificateRevocationListBuilder().issuer_name(ca.subject)
               .last_update(now).next_update(now + timedelta(days=400))
               .add_extension(x509.CRLNumber(number), critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False))
    for entry in revoked:
        builder = builder.add_revoked_certificate(entry)
    return builder.sign(key, SHA256).public_bytes(PEM)


def init(directory, now):
    if any(p.name != REGISTRY + '.maintenance.lock' for p in directory.iterdir()):
        raise ValueError('Каталог уже містить CA або інші файли. Виберіть порожній каталог.')
    password = prompt_password('Новий пароль Device CA: ', confirm=True, minimum=12)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Project 2 Device CA')])
    try:
        end = now.replace(year=now.year + 10)
    except ValueError:  # February 29 in a non-leap target year.
        end = now.replace(year=now.year + 10, day=28)
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(end)
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(key_usage(True), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
          .sign(key, SHA256))
    contents = {KEY: key.private_bytes(PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.BestAvailableEncryption(password)),
                CERT: ca.public_bytes(PEM), CRL: build_crl(ca, key, 1, [], now), REGISTRY: b'[]\n'}
    published = []
    try:
        for name, content in contents.items():
            path = directory / name
            with staged(path, content) as temp:
                publish_new(temp, path)
            published.append(path)
    except OSError:
        for path in published:
            path.unlink()
        raise
    print(f'Device CA створено. SHA-256 {ca.fingerprint(SHA256).hex()}')


def status(record, now):
    if record['status'] == 'revoked':
        return 'revoked'
    return 'active' if datetime.fromisoformat(record['expires_at']) > now else 'expired'


def issue(args, directory, ca, key, records, password, now, forbidden):
    if not re.fullmatch(r'[a-z0-9-]{1,40}', args.name):
        raise ValueError('Ім’я ПК має відповідати [a-z0-9-]{1,40}.')
    if any(r['name'] == args.name and status(r, now) == 'active' for r in records):
        raise ValueError('У цього ПК вже є чинний сертифікат.')
    out = external_path(args.out, forbidden, 'PFX')
    if out.suffix.lower() != '.pfx' or os.path.lexists(args.out) or not out.parent.is_dir():
        raise ValueError('Вкажіть новий файл .pfx у наявному каталозі. Наявні файли зберігаються.')
    pfx_password = prompt_password('Окремий пароль нового PFX: ', confirm=True)
    if pfx_password == password:
        raise ValueError('Для PFX потрібен окремий пароль, відмінний від пароля CA.')
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    serial = secrets.randbits(127) | (1 << 127)
    if any(r['serial'] == f'{serial:x}' for r in records):
        raise ValueError('Колізія серійного номера. Повторіть видачу.')
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, args.name),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Project 2 Devices')])
    end = min(now + timedelta(days=730), ca.not_valid_after_utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(ca.subject)
            .public_key(leaf_key.public_key()).serial_number(serial).not_valid_before(now).not_valid_after(end)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(key_usage(False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca.public_key()), critical=False)
            .sign(key, SHA256))
    encryption = (serialization.PrivateFormat.PKCS12.encryption_builder().kdf_rounds(200_000)
                  .key_cert_algorithm(pkcs12.PBES.PBESv2SHA256AndAES256CBC).hmac_hash(SHA256).build(pfx_password))
    bundle = pkcs12.serialize_key_and_certificates(args.name.encode(), leaf_key, cert, None, encryption)
    record = {'name': args.name, 'serial': f'{serial:x}', 'issued_at': now.isoformat(),
              'expires_at': end.isoformat(), 'sha256': cert.fingerprint(SHA256).hex(), 'status': 'active'}
    # Register first so an interrupted CLI cannot leave a published PFX without a serial to revoke.
    with staged(out, bundle) as temp:
        save_registry(directory, [*records, record])
        try:
            publish_new(temp, out)
        except OSError:
            save_registry(directory, records)
            raise
    print(f'Видано {args.name} до {end:%Y-%m-%d}. SHA-256 {record["sha256"]}')


def update_revocations(args, directory, ca, key, crl, records, now):
    entries = {entry.serial_number: entry for entry in crl}
    if args.command == 'revoke':
        if args.serial:
            if not re.fullmatch(r'[0-9a-fA-F]{1,40}', args.serial):
                raise ValueError('Некоректний серійний номер у hex.')
            matches = [r for r in records if int(r['serial'], 16) == int(args.serial, 16)]
        else:
            matches = [r for r in records if r['name'] == args.name]
        if not matches:
            raise ValueError('Пристрій відсутній у реєстрі.')
        record = matches[-1]  # A reissued name refers to its latest certificate.
        serial = int(record['serial'], 16)
        if serial not in entries:
            entries[serial] = (x509.RevokedCertificateBuilder().serial_number(serial).revocation_date(now)
                               .add_extension(x509.CRLReason(REASONS[args.reason]), critical=False).build())
    number = crl.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number + 1
    replace_file(directory / CRL, build_crl(ca, key, number, entries.values(), now))
    # Publish revocation first. The signed list is authoritative if updating JSON is interrupted.
    sync_revoked(records, entries)
    save_registry(directory, records)
    print(f'Опубліковано CRL №{number}, відкликано {len(entries)}. Перезапустіть завдання LAN.')


def sync_revoked(records, entries):
    for record in records:
        entry = entries.get(int(record['serial'], 16))
        if entry is not None:
            reason = entry.extensions.get_extension_for_class(x509.CRLReason).value.reason
            record.update(status='revoked', revoked_at=entry.revocation_date_utc.isoformat(), reason=reason.value)
        elif record['status'] == 'revoked':
            raise ValueError('CRL не містить відкликання з реєстру. Звірте актуальну пару CRL і devices.json.')


def operate(args):
    forbidden = protected_paths(Settings.read())  # Reads configuration, never opens the database.
    directory = external_path(args.dir, forbidden, 'Каталог Device CA')
    if args.command == 'init':
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError('Каталог Device CA не існує.')
    lock_file = REGISTRY + '.maintenance.lock'
    if any((directory / name).is_symlink() for name in (KEY, CERT, CRL, REGISTRY, lock_file)):
        raise ValueError('Файли Device CA мають бути звичайними файлами захищеного каталогу.')
    with ExitStack() as stack:
        try:
            stack.enter_context(database_lease(directory / REGISTRY, shared=args.command == 'list'))
        except ValueError:
            raise ValueError('Інша операція вже використовує цей Device CA. Повторіть команду.') from None
        now = datetime.now(UTC).replace(microsecond=0)
        if args.command == 'init':
            return init(directory, now)
        ca = single_pem(directory / CERT, b'CERTIFICATE', x509.load_pem_x509_certificate)
        crl = single_pem(directory / CRL, b'X509 CRL', x509.load_pem_x509_crl)
        if crl.issuer != ca.subject or not crl.is_signature_valid(ca.public_key()):
            raise ValueError('Підпис CRL не відповідає Device CA.')
        records = json.loads((directory / REGISTRY).read_text(encoding='utf-8'))
        sync_revoked(records, {entry.serial_number: entry for entry in crl})
        if args.command == 'list':
            print('Пристрій\tСерійний номер\tСтан\tВидано (UTC)\tДіє до (UTC)\tSHA-256')
            labels = {'active': 'чинний', 'expired': 'прострочений', 'revoked': 'відкликаний'}
            for record in records:
                print('\t'.join((record['name'], record['serial'], labels[status(record, now)],
                                 record['issued_at'], record['expires_at'], record['sha256'])))
            print(f'CRL діє до {crl.next_update_utc:%Y-%m-%d %H:%M UTC}, відкликано {len(crl)}.')
            return
        password = prompt_password('Пароль Device CA: ')
        key = serialization.load_pem_private_key((directory / KEY).read_bytes(), password=password)
        if key.public_key() != ca.public_key() or not ca.not_valid_before_utc <= now < ca.not_valid_after_utc:
            raise ValueError('Перевірте строк Device CA та відповідність його ключа.')
        if args.command == 'issue':
            issue(args, directory, ca, key, records, password, now, forbidden)
        else:
            update_revocations(args, directory, ca, key, crl, records, now)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Локальний центр сертифікації пристроїв Project 2')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'issue', 'revoke', 'crl', 'list'):
        sub = commands.add_parser(command)
        sub.add_argument('--dir', type=Path, required=True)
        if command == 'issue':
            sub.add_argument('--name', required=True)
            sub.add_argument('--out', required=True, type=Path)
        if command == 'revoke':
            target = sub.add_mutually_exclusive_group(required=True)
            target.add_argument('--name')
            target.add_argument('--serial')
            sub.add_argument('--reason', required=True, choices=REASONS)
    try:
        operate(parser.parse_args(argv))
    except (getpass.GetPassWarning, EOFError):
        parser.exit(1, 'Для прихованого введення пароля потрібен інтерактивний термінал.\n')
    except (OSError, ValueError, TypeError, KeyError, x509.ExtensionNotFound) as error:
        parser.exit(1, f'Помилка Device CA: {error}\n')


if __name__ == '__main__':
    main()
