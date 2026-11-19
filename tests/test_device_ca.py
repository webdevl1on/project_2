from datetime import timedelta
import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from app.database.maintenance import database_lease
from app.security import device_ca as ca
from tests.device_pki import CA_PASSWORD, PFX_PASSWORD, cli


def test_issue_and_revoke_lifecycle(tmp_path, capsys):
    directory = tmp_path / 'device-ca'
    cli(directory, 'init')
    key_data = (directory / ca.KEY).read_bytes()
    assert key_data.startswith(b'-----BEGIN ENCRYPTED PRIVATE KEY-----')
    with pytest.raises(TypeError):
        serialization.load_pem_private_key(key_data, None)
    key = serialization.load_pem_private_key(key_data, CA_PASSWORD.encode())
    root = x509.load_pem_x509_certificate((directory / ca.CERT).read_bytes())
    root.verify_directly_issued_by(root)
    assert root.public_key() == key.public_key() and root.subject.rfc4514_string() == 'CN=Project 2 Device CA'
    bc = root.extensions.get_extension_for_class(x509.BasicConstraints)
    ku = root.extensions.get_extension_for_class(x509.KeyUsage)
    assert bc.critical and bc.value.ca and bc.value.path_length == 0
    assert ku.critical and ku.value.key_cert_sign and ku.value.crl_sign
    assert root.not_valid_after_utc.year == root.not_valid_before_utc.year + 10

    def crl():
        value = x509.load_pem_x509_crl((directory / ca.CRL).read_bytes())
        assert value.is_signature_valid(root.public_key())
        assert value.next_update_utc - value.last_update_utc == timedelta(days=400)
        return value, value.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number

    initial, first_number = crl()
    assert len(initial) == 0
    out = tmp_path / 'pc.pfx'
    cli(directory, 'issue', '--name', 'foxlys', '--out', out)
    for password in (None, CA_PASSWORD.encode(), b'wrong'):
        with pytest.raises(ValueError):
            pkcs12.load_key_and_certificates(out.read_bytes(), password)
    leaf_key, leaf, extras = pkcs12.load_key_and_certificates(out.read_bytes(), PFX_PASSWORD.encode())
    assert not extras and leaf.public_key() == leaf_key.public_key() and isinstance(leaf_key.curve, ec.SECP256R1)
    leaf.verify_directly_issued_by(root)
    assert leaf.serial_number.bit_length() == 128
    assert leaf.not_valid_after_utc - leaf.not_valid_before_utc == timedelta(days=730)
    assert leaf.not_valid_after_utc <= root.not_valid_after_utc
    assert leaf.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'foxlys'
    assert leaf.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == 'Project 2 Devices'
    assert list(leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [ExtendedKeyUsageOID.CLIENT_AUTH]
    leaf_bc = leaf.extensions.get_extension_for_class(x509.BasicConstraints)
    leaf_ku = leaf.extensions.get_extension_for_class(x509.KeyUsage)
    assert leaf_bc.critical and not leaf_bc.value.ca and leaf_ku.critical and leaf_ku.value.digital_signature
    assert not leaf_ku.value.key_cert_sign and not leaf_ku.value.key_encipherment
    assert leaf.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier == root.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    assert leaf.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    assert json.loads((directory / ca.REGISTRY).read_text())[0]['sha256'] == leaf.fingerprint(hashes.SHA256()).hex()
    with pytest.raises(SystemExit):
        cli(directory, 'issue', '--name', 'foxlys', '--out', tmp_path / 'duplicate.pfx')
    cli(directory, 'revoke', '--serial', f'{leaf.serial_number:X}', '--reason', 'keyCompromise')
    revoked, number = crl()
    entry = revoked.get_revoked_certificate_by_serial_number(leaf.serial_number)
    assert entry.extensions.get_extension_for_class(x509.CRLReason).value.reason == x509.ReasonFlags.key_compromise
    assert number == first_number + 1
    cli(directory, 'crl')
    renewed, renewed_number = crl()
    assert len(renewed) == 1 and renewed_number == number + 1
    cli(directory, 'list')
    output = capsys.readouterr().out
    assert 'foxlys' in output and 'відкликаний' in output and 'UTC' in output
    assert CA_PASSWORD not in output and PFX_PASSWORD not in output
    cli(directory, 'issue', '--name', 'foxlys', '--out', tmp_path / 'replacement.pfx')
    records = json.loads((directory / ca.REGISTRY).read_text())
    assert [r['status'] for r in records] == ['revoked', 'active'] and records[0]['serial'] != records[1]['serial']


def test_ca_paths_passwords_overwrite_and_lock(tmp_path, monkeypatch):
    from app.config import ROOT_DIR
    directory = tmp_path / 'ca'
    for forbidden in (ROOT_DIR, ROOT_DIR / 'app/static'):
        with pytest.raises(SystemExit):
            cli(forbidden, 'init', passwords=[])
    storage = tmp_path / 'docs'
    monkeypatch.setenv('PROJECT2_DOCUMENT_STORAGE', str(storage))
    with pytest.raises(SystemExit):
        cli(storage / 'authority', 'init', passwords=[])
    assert not storage.exists()
    for passwords in (['short'], [CA_PASSWORD, 'different value']):
        with pytest.raises(SystemExit):
            cli(directory, 'init', passwords=passwords)
    cli(directory, 'init')
    before = (directory / ca.KEY).read_bytes()
    with pytest.raises(SystemExit):
        cli(directory, 'init', passwords=[])
    assert before == (directory / ca.KEY).read_bytes()
    out = tmp_path / 'target.pfx'
    for name, passwords in (('PC name', [CA_PASSWORD]), ('pc', ['wrong password']), ('pc', [CA_PASSWORD] * 3)):
        with pytest.raises(SystemExit):
            cli(directory, 'issue', '--name', name, '--out', out, passwords=passwords)
    with database_lease(directory / ca.REGISTRY), pytest.raises(SystemExit):
        cli(directory, 'issue', '--name', 'pc', '--out', out, passwords=[])
    assert not out.exists() and json.loads((directory / ca.REGISTRY).read_text()) == []
    out.write_bytes(b'existing file')
    with pytest.raises(SystemExit):
        cli(directory, 'issue', '--name', 'pc', '--out', out)
    assert out.read_bytes() == b'existing file'


def test_interrupted_registry_write_keeps_revocation_on_retry(tmp_path, monkeypatch):
    directory = tmp_path / 'devices'
    cli(directory, 'init')
    cli(directory, 'issue', '--name', 'one', '--out', tmp_path / 'one.pfx')
    with monkeypatch.context() as changes:
        def unavailable(*args):
            raise OSError('synthetic registry error')
        changes.setattr(ca, 'save_registry', unavailable)
        with pytest.raises(SystemExit):
            cli(directory, 'revoke', '--name', 'one', '--reason', 'superseded')
    assert len(x509.load_pem_x509_crl((directory / ca.CRL).read_bytes())) == 1
    cli(directory, 'crl')
    [record] = json.loads((directory / ca.REGISTRY).read_text())
    assert record['status'] == 'revoked' and record['reason'] == 'superseded'


def test_leaf_lifetime_is_clamped_and_expired_name_can_be_reissued(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from unittest.mock import Mock
    now = datetime.now(UTC).replace(microsecond=0)
    clock = Mock(wraps=datetime)
    clock.now.return_value = now
    monkeypatch.setattr(ca, 'datetime', clock)
    directory = tmp_path / 'ca'
    cli(directory, 'init')
    cli(directory, 'issue', '--name', 'same-pc', '--out', tmp_path / 'first.pfx')
    root = x509.load_pem_x509_certificate((directory / ca.CERT).read_bytes())
    clock.now.return_value = root.not_valid_after_utc - timedelta(days=60)
    out = tmp_path / 'renewal.pfx'
    cli(directory, 'issue', '--name', 'same-pc', '--out', out)
    _, leaf, _ = pkcs12.load_key_and_certificates(out.read_bytes(), PFX_PASSWORD.encode())
    assert leaf.not_valid_after_utc == root.not_valid_after_utc
    assert len(json.loads((directory / ca.REGISTRY).read_text())) == 2


def test_issue_rolls_back_registry_if_output_cannot_be_published(tmp_path, monkeypatch):
    directory = tmp_path / 'devices'
    cli(directory, 'init')
    def denied(*args):
        raise PermissionError('synthetic write error')
    monkeypatch.setattr(ca, 'publish_new', denied)
    out = tmp_path / 'portable.pfx'
    with pytest.raises(SystemExit):
        cli(directory, 'issue', '--name', 'foxlys', '--out', out)
    assert not out.exists() and json.loads((directory / ca.REGISTRY).read_text()) == []
