"""Quiet peer resets in the app.serve loop and device-CRL deadline notices."""
import asyncio
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from app.security import listener_loop
from app.security.device_tls import SCOPE_TRUST, DeviceTrust
from app.templating import device_crl_notice, templates


def trust(days):
    return DeviceTrust(Path('ca.pem'), Path('crl.pem'), b'\x01' * 32, b'\x02' * 32,
                       datetime.now(UTC) + timedelta(days=days, hours=1), 0)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.mark.parametrize('error', [ConnectionResetError(10054, 'reset'), ConnectionAbortedError(10053, 'aborted')])
def test_peer_resets_are_counted_not_reported(error, caplog):
    loop = Mock()
    clock = Clock()
    counter = listener_loop.PeerResetCounter(clock)
    with caplog.at_level(logging.INFO, logger=listener_loop.logger.name):
        for _ in range(5):
            counter.handler(loop, {'message': 'Exception in callback _call_connection_lost', 'exception': error})
        assert loop.default_exception_handler.call_count == 0
        assert caplog.text.count('Клієнт обірвав') == 1 and 'Обірвано клієнтами' not in caplog.text
        clock.now += listener_loop.SUMMARY_SECONDS
        counter.handler(loop, {'exception': error})
    assert 'Обірвано клієнтами зʼєднань за останні 60 хв: 5.' in caplog.text
    assert counter.count == 0


@pytest.mark.parametrize('context', [
    {'message': 'boom', 'exception': RuntimeError('real failure')},
    {'message': 'other OSError', 'exception': OSError('disk')},
    {'message': 'no exception at all'},
])
def test_other_loop_errors_keep_the_default_handler(context):
    loop = Mock()
    listener_loop.PeerResetCounter().handler(loop, context)
    loop.default_exception_handler.assert_called_once_with(context)


def test_lan_event_loop_installs_handler_and_daily_check():
    loop = listener_loop.lan_event_loop()
    try:
        handler = loop.get_exception_handler()
        assert handler.__self__.__class__ is listener_loop.PeerResetCounter
        timers = [h for h in loop._scheduled if not h.cancelled()]
        assert any(h._callback is listener_loop._daily_crl_check for h in timers)
    finally:
        loop.close()


def test_reset_in_a_real_loop_callback_is_silent(caplog):
    loop = listener_loop.lan_event_loop()
    try:
        def fail():
            raise ConnectionResetError(10054, 'synthetic reset')
        with caplog.at_level(logging.DEBUG):
            loop.call_soon(fail)
            loop.run_until_complete(asyncio.sleep(0))
        assert 'Traceback' not in caplog.text and 'synthetic reset' not in caplog.text
    finally:
        loop.close()


@pytest.mark.parametrize('days,level,text', [
    (60, None, None),
    (20, logging.WARNING, 'поновіть CRL'),
    (-2, logging.ERROR, 'прострочено'),
])
def test_daily_crl_check(days, level, text, caplog):
    with caplog.at_level(logging.INFO, logger=listener_loop.logger.name):
        listener_loop.check_crl(trust(days))
        listener_loop.check_crl(None)
    if level is None:
        assert not caplog.records
    else:
        assert caplog.records[-1].levelno == level and text in caplog.text


def request_with(trust_value, role):
    scope = {'type': 'http', 'method': 'GET', 'path': '/admin', 'headers': [], 'query_string': b''}
    if trust_value is not None:
        scope[SCOPE_TRUST] = trust_value
    request = Request(scope)
    user = SimpleNamespace(role=role) if role else None
    return request, user


@pytest.mark.parametrize('days,role,expected', [
    (20, 'master', (20, False)),
    (20, 'admin', (20, False)),
    (3, 'admin', (3, True)),
    (-1, 'master', (-1, True)),
    (20, 'user', None),
    (20, None, None),
    (60, 'admin', None),
])
def test_banner_context_only_for_master_admin_near_deadline(days, role, expected):
    request, user = request_with(trust(days), role)
    notice = device_crl_notice(request, user)
    assert (notice and (notice['days_left'], notice['critical'])) == expected or (notice is None and expected is None)


def test_banner_absent_without_verified_listener():
    request, user = request_with(None, 'master')
    assert device_crl_notice(request, user) is None


@pytest.mark.parametrize('days,css,phrase', [
    (20, 'alert-warning', 'залишилось днів: 20'),
    (3, 'alert-danger', 'залишилось днів: 3'),
    (-1, 'alert-danger', 'прострочено'),
])
def test_banner_template(days, css, phrase):
    request, user = request_with(trust(days), 'admin')
    html = templates.env.get_template('components/device_crl_notice.html').render(ui_device_crl=device_crl_notice(request, user))
    assert css in html and phrase in html and 'device_ca crl' in html and 'Restart-Project2Task.ps1' in html


def test_base_layout_includes_banner():
    source = Path('app/templates/layouts/base.html').read_text(encoding='utf-8')
    assert "{% include 'components/device_crl_notice.html' %}" in source
