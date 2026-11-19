"""Disposable TLS identities shared by the Device CA, listener and LAN tests."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from app.database.settings import Settings
from app.main import network_policy
from app.security import device_ca, network

CA_PASSWORD = 'test only device authority'
PFX_PASSWORD = 'test only portable device'
PEM = serialization.Encoding.PEM


def cli(directory, command, *args, passwords=None):
    if passwords is None:
        passwords = {'init': [CA_PASSWORD] * 2, 'issue': [CA_PASSWORD, PFX_PASSWORD, PFX_PASSWORD],
                     'list': []}.get(command, [CA_PASSWORD])
    with patch.object(device_ca.getpass, 'getpass', side_effect=passwords):
        device_ca.main([command, '--dir', str(directory), *map(str, args)])


def make_authority(cn='Synthetic server CA', *, start=None, end=None, is_ca=True, can_sign=True):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(UTC)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(start or now - timedelta(days=1))
               .not_valid_after(end or now + timedelta(days=800))
               .add_extension(x509.BasicConstraints(is_ca, 0 if is_ca else None), critical=True)
               .add_extension(x509.KeyUsage(True, False, False, False, False, can_sign, can_sign, False, False), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False))
    return builder.sign(key, hashes.SHA256()), key


def sign_leaf(ca, key, *, client=False, expired=False):
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    name = 'sample-device' if client else 'foxlys.local'
    now = datetime.now(UTC)
    builder = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
               .issuer_name(ca.subject).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=4)).not_valid_after(now + timedelta(days=-1 if expired else 10))
               .add_extension(x509.BasicConstraints(False, None), critical=True)
               .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False))
    if not client:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
    return builder.sign(key, hashes.SHA256()), leaf_key


def write_pair(directory, name, cert, key):
    cert_path = directory / (name + '.crt.pem')
    key_path = directory / (name + '.key.pem')
    cert_path.write_bytes(cert.public_bytes(PEM))
    key_path.write_bytes(key.private_bytes(PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_path, key_path


@pytest.fixture
def lan(monkeypatch, tmp_path):
    storage = Settings('production', None, {'documents': tmp_path / 'documents'})
    ca, key = make_authority()
    write_pair(tmp_path, 'server-ca', ca, key)
    cert, server_key = write_pair(tmp_path, 'server', *sign_leaf(ca, key))
    directory = tmp_path / 'devices'
    cli(directory, 'init')
    values = {'BIND_HOST': '0.0.0.0', 'SERVER_NAME': 'foxlys.local', 'PORT': '8443',
              'ALLOWED_NETWORKS': '192.168.50.0/24,fd21:12::/64,fe80::/64',
              'AUTH_ALLOW_LOCAL_HTTP': '0', 'WEBAUTHN_RP_ID': 'foxlys.local',
              'WEBAUTHN_ORIGINS': '["https://foxlys.local:8443"]', 'TLS_CERT': cert, 'TLS_KEY': server_key,
              'CLIENT_CA': directory / device_ca.CERT, 'CLIENT_CRL': directory / device_ca.CRL}
    for name, value in values.items():
        monkeypatch.setenv('PROJECT2_' + name, str(value))
    monkeypatch.setattr(network_policy, 'settings', network.NetworkSettings.read(storage))
    return storage
