"""TLS peers on an ephemeral loopback socket; no external host, proxy, database or Windows store."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import logging
import socket
import ssl
import threading
import time
from unittest.mock import Mock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from fastapi.testclient import TestClient
import pytest
from starlette.responses import Response
import uvicorn

from app import serve
from app.main import Project2API, app, network_policy
from app.security import device_ca, network
from tests.device_pki import CA_PASSWORD, PEM, PFX_PASSWORD, cli, lan, make_authority, sign_leaf, write_pair


@contextmanager
def listener():
    # Capture what the production entry point passes to Uvicorn, then use those
    # exact TLS options and ASGI app with an isolated, pre-bound loopback socket.
    with patch.object(uvicorn, 'run') as launch:
        serve.main([])
    (application,), options = launch.call_args
    reached_http = []
    async def record(scope, receive, send):
        if scope['type'] == 'http':
            reached_http.append(scope['path'])
        await application(scope, receive, send)

    config = uvicorn.Config(record, lifespan='off', ws='none', log_config=None, **options)
    server = uvicorn.Server(config)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while thread.is_alive() and not server.started and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            yield sock.getsockname(), reached_http
        finally:
            server.should_exit = True
            thread.join(5)
            assert not thread.is_alive()


def exchange(address, root, identity=None, version=None):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile=root)
    if identity:
        ctx.load_cert_chain(*identity)
    if version:
        ctx.minimum_version = ctx.maximum_version = version
    with socket.create_connection(address, timeout=5) as sock, ctx.wrap_socket(sock, server_hostname='foxlys.local') as tls:
        tls.sendall(b'GET /auth/login HTTP/1.1\r\nHost: foxlys.local:8443\r\nConnection: close\r\n\r\n')
        with tls.makefile('rb') as response:
            return response.read()


def assert_rejected(address, root, identity, reached, version):
    previously = len(reached)
    try:
        data = exchange(address, root, identity, version)
    except (ssl.SSLError, ConnectionResetError, BrokenPipeError):
        pass  # TLS 1.3 can deliver its fatal alert on the first post-handshake read.
    else:
        assert data == b''
    assert len(reached) == previously


@pytest.mark.parametrize('version', [ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3])
def test_device_admission_at_real_tls_handshake_and_revoke(lan, tmp_path, monkeypatch, version):
    directory = tmp_path / 'devices'
    devices = {}
    for name in ('foxlys', 'second-pc'):
        out = tmp_path / (name + '.pfx')
        cli(directory, 'issue', '--name', name, '--out', out)
        key, cert, _ = pkcs12.load_key_and_certificates(out.read_bytes(), PFX_PASSWORD.encode())
        devices[name] = write_pair(tmp_path, name, cert, key)

    root = tmp_path / 'server-ca.crt.pem'
    server_ca = x509.load_pem_x509_certificate(root.read_bytes())
    server_ca_key = serialization.load_pem_private_key((tmp_path / 'server-ca.key.pem').read_bytes(), None)
    other_ca, other_key = make_authority('Unrelated TLS CA')
    device_root = x509.load_pem_x509_certificate((directory / device_ca.CERT).read_bytes())
    signing_key = serialization.load_pem_private_key((directory / device_ca.KEY).read_bytes(), CA_PASSWORD.encode())
    foreign = write_pair(tmp_path, 'foreign', *sign_leaf(other_ca, other_key, client=True))
    server_issued = write_pair(tmp_path, 'wrong-ca', *sign_leaf(server_ca, server_ca_key, client=True))
    expired = write_pair(tmp_path, 'expired', *sign_leaf(device_root, signing_key, client=True, expired=True))
    wrong_eku = write_pair(tmp_path, 'wrong-usage', *sign_leaf(device_root, signing_key))

    def allowed(address, identity):
        response = exchange(address, root, identity, version)
        headers, body = response.split(b'\r\n\r\n', 1)
        assert headers.startswith(b'HTTP/1.1 200') and body
        assert b'\r\nstrict-transport-security: max-age=31536000' in headers.lower()

    with listener() as (address, reached):
        allowed(address, devices['foxlys'])
        for invalid in (None, foreign, server_issued, expired, wrong_eku):
            assert_rejected(address, root, invalid, reached, version)
        assert reached == ['/auth/login']
    cli(directory, 'revoke', '--name', 'foxlys', '--reason', 'cessationOfOperation')
    settings = network.NetworkSettings.read(lan)
    monkeypatch.setattr(network_policy, 'settings', settings)
    with listener() as (address, reached):
        assert_rejected(address, root, devices['foxlys'], reached, version)
        allowed(address, devices['second-pc'])
        assert reached == ['/auth/login']


@pytest.mark.parametrize('variable', ['CLIENT_CA', 'CLIENT_CRL'])
def test_missing_device_material_rejected_only_for_lan(lan, monkeypatch, variable):
    monkeypatch.delenv('PROJECT2_' + variable)
    with pytest.raises(ValueError, match='PROJECT2_CLIENT_'):
        network.NetworkSettings.read(lan)
    monkeypatch.setenv('PROJECT2_BIND_HOST', '127.0.0.1')
    assert network.NetworkSettings.read(lan).device_trust is None


@pytest.mark.parametrize('case', ['expired-crl', 'future-crl', 'foreign-crl', 'server-ca', 'extra-ca', 'ca-in-crl',
                                  'expired-ca', 'leaf-as-ca', 'missing-key-cert-sign'])
def test_bad_device_trust_never_starts(lan, tmp_path, monkeypatch, case):
    now = datetime.now(UTC)
    root_path, crl_path = (tmp_path / 'devices' / n for n in (device_ca.CERT, device_ca.CRL))
    ca = x509.load_pem_x509_certificate(root_path.read_bytes())
    key = serialization.load_pem_private_key((root_path.parent / device_ca.KEY).read_bytes(), CA_PASSWORD.encode())
    start, end = now - timedelta(days=2), now + timedelta(days=400)
    if case == 'expired-crl':
        end = now - timedelta(days=1)
    elif case == 'future-crl':
        start = now + timedelta(days=1)
    elif case == 'foreign-crl':
        _, key = make_authority()
    elif case == 'server-ca':
        ca = x509.load_pem_x509_certificate((tmp_path / 'server-ca.crt.pem').read_bytes())
        key = serialization.load_pem_private_key((tmp_path / 'server-ca.key.pem').read_bytes(), None)
    elif case in ('expired-ca', 'leaf-as-ca', 'missing-key-cert-sign'):
        ca, key = make_authority(is_ca=case != 'leaf-as-ca', can_sign=case != 'missing-key-cert-sign',
                                 start=now-timedelta(days=4), end=now-timedelta(days=1) if case == 'expired-ca' else None)
    root_path.write_bytes(ca.public_bytes(PEM) + ((tmp_path / 'server-ca.crt.pem').read_bytes() if case == 'extra-ca' else b''))
    crl = x509.CertificateRevocationListBuilder().issuer_name(ca.subject).last_update(start).next_update(end).sign(key, hashes.SHA256())
    crl_path.write_bytes(crl.public_bytes(PEM) + (ca.public_bytes(PEM) if case == 'ca-in-crl' else b''))
    with pytest.raises(ValueError) as error:
        network.NetworkSettings.read(lan)
    if case == 'expired-crl':
        assert 'python -m app.security.device_ca crl' in str(error.value)


def test_crl_deadline_warns_at_start_and_in_log(lan, tmp_path, monkeypatch, caplog, capsys):
    directory = tmp_path / 'devices'
    ca = x509.load_pem_x509_certificate((directory / device_ca.CERT).read_bytes())
    key = serialization.load_pem_private_key((directory / device_ca.KEY).read_bytes(), CA_PASSWORD.encode())
    now = datetime.now(UTC)
    crl = x509.CertificateRevocationListBuilder().issuer_name(ca.subject).last_update(now).next_update(now+timedelta(days=29)).sign(key, hashes.SHA256())
    (directory / device_ca.CRL).write_bytes(crl.public_bytes(PEM))
    with caplog.at_level(logging.WARNING, logger=network.logger.name):
        settings = network.NetworkSettings.read(lan)
    monkeypatch.setattr(network_policy, 'settings', settings)
    monkeypatch.setattr(serve.uvicorn, 'run', Mock())
    serve.main([])
    for text in (caplog.text, capsys.readouterr().out):
        assert 'поновіть CRL' in text and ca.fingerprint(hashes.SHA256()).hex()[:16] in text and 'відкликано 0' in text


def test_lan_listener_marker_cannot_be_supplied_as_an_http_header(lan):
    client = TestClient(app, client=('127.0.0.1', 31000), base_url='https://foxlys.local:8443')
    try:
        response = client.get('/auth/login', headers={'X-Client-Cert': 'present', 'project2.device_trust': 'true'})
    finally:
        client.close()
    assert response.status_code == 403 and not response.content


@pytest.mark.parametrize('peer,path,host,status', [
    ('192.168.50.3', '/auth/login', 'foxlys.local', 200),
    ('192.168.50.3', '/persons', 'foxlys.local', 303),
    ('192.168.50.3', '/auth/login', 'unknown.local', 400),
    ('192.168.51.3', '/auth/login', 'foxlys.local', 403),
    ('192.168.50.3', '/missing', 'foxlys.local', 404),
    ('192.168.50.3', '/static/js/login.js', 'foxlys.local', 200),
])
def test_hsts_on_https_responses(lan, peer, path, host, status):
    client = TestClient(network_policy.settings.device_trust.application(app), base_url='https://foxlys.local',
                        client=(peer, 4567), follow_redirects=False)
    response = client.get(path, headers={'Host': host, 'Accept': 'text/html'})
    assert response.status_code == status
    assert response.headers.get_list('strict-transport-security') == ['max-age=31536000']
    client.close()


def test_hsts_on_unhandled_error_and_existing_header_and_loopback_http(lan, monkeypatch):
    probe = Project2API()

    @probe.get('/failure')
    def failure():
        raise RuntimeError('synthetic failure')

    @probe.get('/header')
    def existing():
        return Response(headers={'Strict-Transport-Security': 'max-age=31536000'})

    https = TestClient(network_policy.settings.device_trust.application(probe), raise_server_exceptions=False,
                       base_url='https://foxlys.local', client=('127.0.0.1', 4000))
    for path, expected in (('/failure', 500), ('/header', 200)):
        response = https.get(path)
        assert response.status_code == expected
        assert response.headers.get_list('strict-transport-security') == ['max-age=31536000']
    https.close()
    monkeypatch.setattr(network_policy, 'settings', replace(network_policy.settings, loopback_only=True, device_trust=None))
    monkeypatch.setenv('PROJECT2_AUTH_ALLOW_LOCAL_HTTP', '1')
    client = TestClient(app, base_url='http://localhost:8000', client=('127.0.0.1', 4000))
    response = client.get('/auth/login')
    assert response.status_code == 200 and 'strict-transport-security' not in response.headers
    client.close()


@pytest.mark.parametrize('variable', ['CLIENT_CA', 'CLIENT_CRL'])
def test_client_trust_files_use_private_storage_path_checks(lan, tmp_path, monkeypatch, variable):
    directory = lan.paths['documents']
    directory.mkdir()
    path = directory / 'trust.pem'
    path.write_bytes(b'synthetic storage marker')
    alias = tmp_path / 'public-looking.pem'
    alias.symlink_to(path)
    monkeypatch.setenv('PROJECT2_' + variable, str(alias))
    with pytest.raises(ValueError, match='поза репозиторієм'):
        network.NetworkSettings.read(lan)
