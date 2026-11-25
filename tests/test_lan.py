"""LAN admission tests use synthetic ASGI peers, interface snapshots and a clock."""
from dataclasses import replace
from ipaddress import ip_address, ip_network
import logging
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest
from fastapi.testclient import TestClient

from tests.device_pki import lan
from app.main import app, network_policy
from app.security import network
from app import serve


def request(peer, path='/auth/login', host='foxlys.local:8443', scheme='https', headers=None):
    trust = network_policy.settings.device_trust
    client = TestClient(trust.application(app) if trust else app, base_url=f'{scheme}://foxlys.local:8443', client=(peer, 32123),
                        follow_redirects=False)
    try:
        return client.get(path, headers=[('Host', host), *(headers or [])])
    finally:
        client.close()


@pytest.mark.parametrize('peer,host', [('192.168.50.8', 'foxlys.local:8443'),
                                      ('192.168.50.8', 'FOXLYS.LOCAL'), ('::ffff:192.168.50.8', 'foxlys.local'),
                                      ('fd21:12::c', 'foxlys.local'), ('fe80::c%7', 'foxlys.local'),
                                      ('127.0.0.1', 'localhost'), ('::1', '[::1]:8443'),
                                      ('127.0.0.2', '127.0.0.1:8443')])
def test_allowed_login(lan, peer, host):
    assert request(peer, host=host).status_code == 200


@pytest.mark.parametrize('path', ['/static/js/login.js', '/auth/login', '/no-such-route'])
@pytest.mark.parametrize('peer', ['192.168.51.8', '8.8.8.8', '::ffff:8.8.8.8', '2001:4860::1', 'testclient'])
def test_peer_denial_precedes_all_routes_and_logs_only_path(lan, path, peer, caplog):
    with caplog.at_level(logging.WARNING, logger=network.logger.name):
        response = request(peer, path + '?secret=must-stay-private', headers=[
            ('X-Forwarded-For', '192.168.50.8'), ('Forwarded', 'for=127.0.0.1;proto=https'), ('X-Real-IP', '127.0.0.1')])
    assert response.status_code == 403 and response.content == b'' and 'set-cookie' not in response.headers
    assert path in caplog.text and 'must-stay-private' not in caplog.text


@pytest.mark.parametrize('host', ['outside.local', 'localhost:8443', '127.0.0.1', '[::1]',
                                 'foxlys.local@other', 'foxlys.local:bad', 'foxlys.local:65536', ''])
def test_bad_host(lan, host):
    response = request('192.168.50.8', '/static/js/login.js', host=host)
    assert response.status_code == 400 and not response.content and 'set-cookie' not in response.headers


def test_duplicate_host_https_and_slash_redirect(lan):
    assert request('192.168.50.8', headers=[('Host', 'other.local')]).status_code == 400
    for path in ('/static/js/login.js', '/auth/login', '/missing'):
        assert request('192.168.50.8', path, scheme='http', headers=[('X-Forwarded-Proto', 'https')]).status_code == 403
    result = request('192.168.50.8', '/auth/login/?tab=a')
    assert result.status_code == 307 and result.headers['location'] == '/auth/login?tab=a'
    assert request('192.168.50.8', '/static/js/login.js').status_code == 200
    assert request('192.168.50.8', '/missing').status_code == 404
    assert request('192.168.50.8', '/auth/me').status_code == 401


def test_auto_refreshes_private_prefixes_from_active_interfaces_and_fails_closed(lan, monkeypatch):
    enabled = SimpleNamespace(isup=True)
    stats = {'active': enabled, 'unplugged': SimpleNamespace(isup=False)}
    def addr(value, mask):
        return SimpleNamespace(family=socket.AF_INET6 if ':' in value else socket.AF_INET,
                               address=value, netmask=mask)
    addresses = {'active': [addr('10.22.1.2', '255.255.255.0'), addr('8.8.8.8', '255.255.255.0'),
                            addr('169.254.2.4', '255.255.0.0'), addr('fe80::a%12', 'ffff:ffff:ffff:ffff::'),
                            addr('fd00::2', '64'), addr('2001:4860::4', '64'), addr('10.0.0.2', None),
                            addr('10.1.1.2', '0.0.0.0'), addr('fd00::4', 'ffff:0:ffff::')],
                 'unplugged': [addr('192.168.1.2', '24')]}
    monkeypatch.setattr(network, 'windows_prefixes', network.psutil_prefixes)
    interfaces = Mock(return_value=addresses)
    monkeypatch.setattr(network.psutil, 'net_if_stats', lambda: stats)
    monkeypatch.setattr(network.psutil, 'net_if_addrs', interfaces)
    clock = [20.0]
    policy = network.NetworkPolicy(replace(network_policy.settings, networks=None), clock=lambda: clock[0])
    assert set(map(str, policy.allowed_networks())) == {'10.22.1.0/24', '169.254.0.0/16', 'fe80::/64', 'fd00::/64'}
    addresses['active'] = [addr('192.168.5.10', '24')]
    clock[0] += 59.9
    assert policy.allows(ip_address('10.22.1.8')) and interfaces.call_count == 1
    clock[0] = 80.0
    assert not policy.allows(ip_address('10.22.1.8')) and policy.allows(ip_address('192.168.5.42'))
    assert interfaces.call_count == 2
    interfaces.side_effect = OSError('synthetic failure')
    clock[0] += 60
    assert not policy.allows(ip_address('192.168.5.42')) and policy.allows(ip_address('::1'))


@pytest.mark.parametrize('name,value', [('SERVER_NAME', ''), ('SERVER_NAME', 'localhost'), ('SERVER_NAME', '192.168.1.5'),
                                        ('TLS_CERT', ''), ('TLS_KEY', ''), ('TLS_KEY', '/missing/server.key'),
                                        ('AUTH_ALLOW_LOCAL_HTTP', '1'), ('PORT', '65536'), ('BIND_HOST', '*'),
                                        ('WEBAUTHN_RP_ID', 'other.local'), ('WEBAUTHN_ORIGINS', '["https://foxlys.local"]')])
def test_invalid_listener_fails_at_startup(lan, monkeypatch, name, value):
    monkeypatch.setenv('PROJECT2_' + name, value)
    with pytest.raises(ValueError, match='PROJECT2_'):
        network.NetworkSettings.read(lan)


@pytest.mark.parametrize('value', ['8.8.8.0/24', '0.0.0.0/0', '::/0', '2001:4860::/32', '::ffff:0:0/96',
                                   '192.0.0.0/24', '100.64.0.0/10', '10.0.0.0/7', '10.0.0.0/8,', '10.1.1.2'])
def test_public_mixed_or_invalid_cidrs_rejected(lan, monkeypatch, value):
    monkeypatch.setenv('PROJECT2_ALLOWED_NETWORKS', value)
    with pytest.raises(ValueError, match='PROJECT2_ALLOWED_NETWORKS'):
        network.NetworkSettings.read(lan)


def test_tls_paths_cannot_be_in_repo_data_or_aliased_to_them(lan, tmp_path, monkeypatch):
    data = lan.paths['documents']; data.mkdir()
    inside = data / 'private.pem'; inside.write_text('fixture')
    alias = tmp_path / 'alias'; alias.symlink_to(inside)
    for path in (inside, alias, Path(__file__), network.ROOT_DIR / 'app/static/js/login.js'):
        monkeypatch.setenv('PROJECT2_TLS_KEY', str(path))
        with pytest.raises(ValueError, match='поза репозиторієм'):
            network.NetworkSettings.read(lan)


def test_tls_key_outside_optional_emergency_storage(lan, tmp_path, monkeypatch):
    import json
    config = tmp_path / 'backup.json'
    config.write_text(json.dumps({'emergency_root': str(tmp_path / 'excel')}))
    key = tmp_path / 'excel/key.pem'
    key.parent.mkdir(); key.write_text('fixture')
    monkeypatch.setenv('PROJECT2_BACKUP_CONFIG', str(config))
    monkeypatch.setenv('PROJECT2_TLS_KEY', str(key))
    with pytest.raises(ValueError, match='PROJECT2_TLS_KEY'):
        network.NetworkSettings.read(lan)


def test_windows_discovery_uses_connected_interface_prefixes_without_a_shell(monkeypatch, tmp_path):
    run = Mock(return_value=SimpleNamespace(stdout=b'192.168.40.2/24\r\nfd01::ab/72\r\nfe80::1%7/64\r\n'))
    monkeypatch.setenv('SystemRoot', str(tmp_path))
    monkeypatch.setattr(network.subprocess, 'run', run)
    assert list(network.windows_prefixes()) == [('192.168.40.2', '24'), ('fd01::ab', '72'), ('fe80::1%7', '64')]
    command = run.call_args.args[0]
    assert 'Get-NetIPInterface -ConnectionState Connected' in command[-1]
    assert 'PrefixLength' in command[-1] and '-NoProfile' in command


def test_listener_defaults_and_443_origin(lan, monkeypatch):
    monkeypatch.delenv('PROJECT2_PORT')
    assert network.NetworkSettings.read(lan).port == 8443
    monkeypatch.setenv('PROJECT2_PORT', '443')
    monkeypatch.setenv('PROJECT2_WEBAUTHN_ORIGINS', '["https://foxlys.local"]')
    assert network.NetworkSettings.read(lan).port == 443
    for name in ('BIND_HOST', 'PORT', 'TLS_KEY', 'TLS_CERT', 'SERVER_NAME', 'ALLOWED_NETWORKS'):
        monkeypatch.delenv('PROJECT2_' + name)
    config = network.NetworkSettings.read(lan)
    assert config.bind_host == '127.0.0.1' and config.port == 8000 and config.cert is None
    assert config.loopback_only and config.networks is None


def test_serve_passes_direct_tls_settings_without_forwarding_or_secrets(lan, monkeypatch, capsys, tmp_path):
    run = Mock(); monkeypatch.setattr(serve.uvicorn, 'run', run)
    serve.main([])
    cfg = network_policy.settings
    run.assert_called_once_with(ANY, host='0.0.0.0', port=8443, loop='app.security.listener_loop:lan_event_loop',
                                ssl_certfile=str(cfg.cert), ssl_keyfile=str(cfg.key),
                                ssl_context_factory=cfg.device_trust.ssl_context, proxy_headers=False, forwarded_allow_ips='', server_header=False,
                                reload=False, workers=1, access_log=False)
    output = capsys.readouterr().out
    assert 'https://foxlys.local:8443' in output and '192.168.50.0/24' in output and 'key.pem' not in output
    from app.security import listener_loop
    assert listener_loop._device_trust is cfg.device_trust
    log = tmp_path / 'task.log'
    serve.main(['--log-file', str(log)])
    assert 'https://foxlys.local:8443' in log.read_text()


def test_launcher_reads_selected_dotenv_and_loads_real_tls_without_opening_a_socket(lan, tmp_path):
    import os
    import subprocess
    import sys
    # The LAN fixture provides a signed server certificate and a separate Device CA/CRL.
    options = ('BIND_HOST', 'PORT', 'SERVER_NAME', 'ALLOWED_NETWORKS', 'TLS_CERT', 'TLS_KEY',
               'CLIENT_CA', 'CLIENT_CRL', 'WEBAUTHN_RP_ID', 'WEBAUTHN_ORIGINS')
    settings = {'PROJECT2_' + name: os.environ['PROJECT2_' + name] for name in options}
    settings.update(PROJECT2_ENV='testing', DATABASE_URL='sqlite:///:memory:')
    file = tmp_path / 'server.env'
    file.write_text('\n'.join(f'{k}={v}' for k, v in settings.items()))
    stub = '''import runpy, uvicorn

def check(app, **kwargs):
    config = uvicorn.Config(app, **kwargs)
    config.load()
    assert config.ssl is not None and config.port == 8443 and config.host == '0.0.0.0'
    assert not config.proxy_headers
    import ssl
    assert config.ssl.verify_mode == ssl.CERT_REQUIRED and config.ssl.verify_flags & ssl.VERIFY_CRL_CHECK_LEAF
    print('TLS loaded')
uvicorn.run = check
runpy.run_module('app.serve',run_name='__main__')'''
    env = {k: v for k, v in os.environ.items() if not k.startswith('PROJECT2_') and k != 'DATABASE_URL'}
    # Only Config.load runs; no listener, database or real network is used.
    cmd = [sys.executable, '-c', stub, '--env-file', str(file)]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and 'TLS loaded' in result.stdout, result.stderr
    file.write_text(file.read_text().replace('PROJECT2_WEBAUTHN_RP_ID=foxlys.local', 'PROJECT2_WEBAUTHN_RP_ID=old.local'))
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and 'PROJECT2_WEBAUTHN_RP_ID' in result.stderr and 'TLS loaded' not in result.stdout


def test_background_task_captures_both_streams_and_rotates_logs(lan, monkeypatch, tmp_path):
    import sys
    log = tmp_path / 'server.log'
    log.write_bytes(b'old-run\n' + b' ' * (5 * 1024 * 1024))

    def output(*args, **kwargs):
        print('synthetic stdout')
        print('synthetic stderr', file=sys.stderr)

    monkeypatch.setattr(serve.uvicorn, 'run', output)
    serve.main(['--log-file', str(log)])
    current = log.read_text(encoding='utf-8')
    assert 'synthetic stdout' in current and 'synthetic stderr' in current
    assert (tmp_path / 'server.log.1').read_bytes().startswith(b'old-run')


def test_boot_time_discovery_failure_retries_every_10_seconds(caplog):
    clock = [100.0]
    calls = []
    results = [OSError('network not ready'), (), (ip_network('192.168.0.0/24'),)]

    def discover():
        calls.append(clock[0])
        result = results.pop(0) if results else (ip_network('192.168.0.0/24'),)
        if isinstance(result, Exception):
            raise result
        return result

    settings = replace(network_policy.settings, networks=None, loopback_only=False)
    with caplog.at_level('INFO', logger=network.logger.name):
        policy = network.NetworkPolicy(settings, discover=discover, clock=lambda: clock[0])
        client = ip_address('192.168.0.20')
        assert not policy.allows(client) and len(calls) == 1
        clock[0] += 9.9
        assert not policy.allows(client) and len(calls) == 1
        clock[0] += 0.1  # failed: retry after 10 s; an empty result is retried the same way
        assert not policy.allows(client) and len(calls) == 2
        clock[0] += 10
        assert policy.allows(client) and len(calls) == 3
        clock[0] += 59
        assert policy.allows(client) and len(calls) == 3  # healthy: back to the 60 s interval
        clock[0] += 1
        assert policy.allows(client) and len(calls) == 4
    warnings = [r for r in caplog.records if 'Не вдалося прочитати' in r.getMessage()]
    assert len(warnings) == 1 and 'Повтор кожні 10 с' in warnings[0].getMessage()
    assert 'Мережеві інтерфейси прочитано: 192.168.0.0/24.' in caplog.text
