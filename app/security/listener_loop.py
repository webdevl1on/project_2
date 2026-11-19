"""Event loop for python -m app.serve.

On Windows the Proactor loop reports every client-side connection reset
(a PC without a device certificate, a browser closing a spare socket) as an
unhandled callback exception with a traceback. Those resets are counted and
summarised instead; every other loop error keeps the default handler.
The loop also re-checks the device CRL deadline once a day, because a
long-running server would otherwise warn only at start.
"""
import asyncio
import logging
import time

from uvicorn.loops.asyncio import asyncio_loop_factory

logger = logging.getLogger('uvicorn.error.project2.lan')
PEER_RESETS = (ConnectionResetError, ConnectionAbortedError)
SUMMARY_SECONDS = 3600
CRL_CHECK_SECONDS = 24 * 3600
_device_trust = None


def configure(trust):
    """Called by app.serve before Uvicorn creates the loop."""
    global _device_trust
    _device_trust = trust


class PeerResetCounter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.count = 0
        self.since = None

    def handler(self, loop, context):
        if isinstance(context.get('exception'), PEER_RESETS):
            self.record()
            return
        loop.default_exception_handler(context)

    def record(self):
        now = self.clock()
        if self.since is None:
            self.since = now
            logger.info('Клієнт обірвав зʼєднання (зокрема ПК без сертифіката пристрою). '
                        'Далі — підсумок не частіше разу на годину.')
            return
        self.count += 1
        if now - self.since >= SUMMARY_SECONDS:
            logger.info('Обірвано клієнтами зʼєднань за останні %d хв: %d.', round((now - self.since) / 60), self.count)
            self.count = 0
            self.since = now


def check_crl(trust):
    if trust is None or not trust.renewal_due:
        return
    days = trust.days_left()
    if days < 0:
        logger.error('CRL пристроїв прострочено: нові зʼєднання LAN відхиляються. '
                     'Поновіть: python -m app.security.device_ca crl --dir <каталог CA> і перезапустіть завдання.')
    else:
        logger.warning(trust.summary())


def _daily_crl_check(loop):
    check_crl(_device_trust)
    loop.call_later(CRL_CHECK_SECONDS, _daily_crl_check, loop)


def lan_event_loop():
    loop = asyncio_loop_factory(use_subprocess=False)()
    loop.set_exception_handler(PeerResetCounter().handler)
    # The start-up check already ran in NetworkSettings.read.
    loop.call_later(CRL_CHECK_SECONDS, _daily_crl_check, loop)
    return loop
