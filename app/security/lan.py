"""Outermost ASGI boundary. The launcher disables all proxy header processing."""
from ipaddress import IPv6Address, ip_address
import re
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import Response

from app.security.accounts import secure_transport
from app.security.network import NetworkPolicy, logger

HOST = re.compile(r'(?P<name>[a-zA-Z0-9.-]+|\[::1\])(?::(?P<port>[0-9]{1,5}))?\Z')
LOCAL_NAMES = {'localhost', '127.0.0.1', '[::1]'}


def permitted_host(headers, server_name, local):
    values = Headers(raw=headers).getlist('host')
    match = HOST.fullmatch(values[0]) if len(values) == 1 else None
    if not match or (match['port'] is not None and not 1 <= int(match['port']) <= 65535):
        return False
    name = match['name'].lower()
    if name in LOCAL_NAMES:
        return local
    return name == server_name


def peer_address(client):
    if not client:
        return None
    try:
        address = ip_address(client[0])
    except ValueError:
        return None
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


class LanMiddleware:
    def __init__(self, app, policy: NetworkPolicy):
        self.app = app
        self.policy = policy

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        address = peer_address(scope.get('client'))
        # A Windows adapter refresh can launch PowerShell. Keep it off the ASGI event loop.
        if (address is not None and address.is_private and not address.is_loopback
                and self.policy.settings.networks is None and not self.policy.settings.loopback_only):
            allowed = await run_in_threadpool(self.policy.allows, address)
        else:
            allowed = address is not None and self.policy.allows(address)
        if not allowed:
            logger.warning('Відхилено мережевий запит IP=%s шлях=%r', address, scope['path'])
            status = 403
        elif not permitted_host(scope['headers'], self.policy.settings.server_name, address.is_loopback):
            status = 400
        elif scope['type'] == 'websocket':
            if scope['scheme'] == 'wss':
                return await self.app(scope, receive, send)
            status = 403
        else:
            try:
                secure_transport(Request(scope))
            except HTTPException as error:
                status = error.status_code
            else:
                return await self.app(scope, receive, self.relative_redirects(send))
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        await Response(status_code=status, headers={'Cache-Control': 'no-store'})(scope, receive, send)

    @staticmethod
    def relative_redirects(send):
        async def send_response(message):
            if message['type'] == 'http.response.start' and message['status'] in (307, 308):
                # Starlette's trailing-slash redirect normally echoes the HTTP authority.
                headers = MutableHeaders(scope=message)
                location = headers.get('location', '')
                if location.startswith(('http://', 'https://')):
                    target = urlsplit(location)
                    headers['location'] = '/' + target.path.lstrip('/') + (('?' + target.query) if target.query else '')
            await send(message)
        return send_response
