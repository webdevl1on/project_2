"""Direct LAN listener configuration and the networks of active interfaces."""
from collections.abc import Callable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
from threading import Lock
import time

import psutil

from app.config import ROOT_DIR
from app.database.settings import Settings
from app.security.device_tls import DeviceTrust
from app.security.mfa_config import relying_party

Address = IPv4Address | IPv6Address
Network = IPv4Network | IPv6Network
DNS_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.ASCII)
V6_PRIVATE = tuple(map(ip_network, ('fc00::/7', 'fe80::/10', '::1/128')))
# These globally reachable anycast addresses are inside an otherwise private IANA block.
V4_PUBLIC_EXCEPTIONS = (IPv4Address('192.0.0.9'), IPv4Address('192.0.0.10'))
logger = logging.getLogger('uvicorn.error.project2.lan')


def private_network(network: Network) -> bool:
    if isinstance(network, IPv6Network):
        return any(network.subnet_of(block) for block in V6_PRIVATE)
    return network.is_private and not any(address in network for address in V4_PUBLIC_EXCEPTIONS)


def windows_prefixes():
    # psutil 7.2.2 does not supply reliable IPv6 netmasks on Windows. The
    # built-in NetTCPIP module supplies the actual on-link prefix for both families.
    command = """
$ErrorActionPreference = 'Stop'
$connected = @{}
foreach ($nic in Get-NetIPInterface -ConnectionState Connected -PolicyStore ActiveStore) {
    $connected["$($nic.InterfaceIndex)/$($nic.AddressFamily)"] = $true
}
foreach ($ip in Get-NetIPAddress -PolicyStore ActiveStore) {
    if ($connected.ContainsKey("$($ip.InterfaceIndex)/$($ip.AddressFamily)") -and
        $ip.AddressState -in @('Preferred','Deprecated')) {
        '{0}/{1}' -f $ip.IPAddress, $ip.PrefixLength
    }
}
"""

    shell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', command],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=True)
    for line in result.stdout.decode('ascii').splitlines():
        address, _, prefix = line.strip().partition('/')
        yield address, prefix


def psutil_prefixes():
    stats = psutil.net_if_stats()
    for name, addresses in psutil.net_if_addrs().items():
        if name in stats and stats[name].isup:
            for entry in addresses:
                if entry.family in (socket.AF_INET, socket.AF_INET6) and entry.netmask:
                    yield entry.address, entry.netmask


def interface_networks() -> tuple[Network, ...]:
    networks = set()
    prefixes = windows_prefixes if os.name == 'nt' else psutil_prefixes
    for value, mask in prefixes():
        try:
            address = ip_address(value.partition('%')[0])
            if address.is_loopback or address.is_unspecified or not address.is_private or not mask:
                continue
            # ip_network accepts IPv6 prefix lengths, but not expanded IPv6 netmasks.
            if ':' in mask:
                bits = f'{int(IPv6Address(mask)):0128b}'
                if '01' in bits:
                    continue
                mask = bits.count('1')
            network = ip_network((address, mask), strict=False)
        except ValueError:
            continue
        if private_network(network):
            networks.add(network)
    return tuple(sorted(networks, key=lambda n: (n.version, int(n.network_address), n.prefixlen)))


def explicit_networks(value: str) -> tuple[Network, ...] | None:
    if value == 'auto':
        return None
    try:
        entries = [item.strip() for item in value.split(',')]
        if any('/' not in entry for entry in entries):
            raise ValueError
        networks = tuple(dict.fromkeys(ip_network(entry) for entry in entries))
        if not all(map(private_network, networks)):
            raise ValueError
    except ValueError:
        raise ValueError('PROJECT2_ALLOWED_NETWORKS потребує auto або списку приватних CIDR.') from None
    return networks


def dns_name(value: str) -> bool:
    return (0 < len(value) <= 253 and not value.replace('.', '').isdigit()
            and all(DNS_LABEL.fullmatch(label) for label in value.split('.')))


def protected_paths(storage: Settings) -> tuple[Path, ...]:
    roots = [ROOT_DIR, *storage.paths.values()]
    backup_config = os.environ.get('PROJECT2_BACKUP_CONFIG')
    if backup_config:
        # The optional recovery and plaintext emergency stores also hold application data.
        try:
            data = json.loads(Path(backup_config).read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict):
                raise ValueError
            roots.extend(Path(data[k]).resolve() for k in ('secrets', 'staging', 'external', 'drill_root', 'emergency_root') if data.get(k))
        except (OSError, TypeError, ValueError):
            raise ValueError('Не вдалося перевірити каталоги сховищ із PROJECT2_BACKUP_CONFIG для TLS.') from None
    return tuple(roots)


def external_path(path: Path, forbidden: tuple[Path, ...], name: str) -> Path:
    path = path.absolute()
    resolved = path.resolve()
    if any(p.is_relative_to(root) for p in (path, resolved) for root in forbidden):
        raise ValueError(f'{name} має бути поза репозиторієм, static і каталогами даних.')
    return resolved


def tls_file(name: str, forbidden: tuple[Path, ...]) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    resolved = external_path(Path(value), forbidden, name)
    if not resolved.is_file():
        raise ValueError(f'{name} має вказувати на доступний файл PEM.')
    return resolved


@dataclass(frozen=True)
class NetworkSettings:
    bind_host: str
    loopback_only: bool
    port: int
    server_name: str
    cert: Path | None
    key: Path | None
    networks: tuple[Network, ...] | None
    device_trust: DeviceTrust | None = None

    @classmethod
    def read(cls, storage: Settings):
        bind = os.environ.get('PROJECT2_BIND_HOST', '127.0.0.1').strip().lower()
        try:
            loopback = ip_address(bind).is_loopback
        except ValueError:
            if not dns_name(bind):
                raise ValueError('Некоректний PROJECT2_BIND_HOST.') from None
            loopback = bind == 'localhost'
        try:
            port = int(os.environ.get('PROJECT2_PORT', 8000 if loopback else 8443))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            raise ValueError('PROJECT2_PORT має бути цілим від 1 до 65535.') from None
        name = os.environ.get('PROJECT2_SERVER_NAME', '').strip().lower()
        if (name and not dns_name(name)) or (not loopback and name in ('', 'localhost')):
            raise ValueError('Для LAN вкажіть DNS-ім’я сервера в PROJECT2_SERVER_NAME, наприклад foxlys.local.')
        if not loopback and storage.environment == 'production' and os.environ.get('PROJECT2_AUTH_ALLOW_LOCAL_HTTP') == '1':
            raise ValueError('Для production LAN вимкніть PROJECT2_AUTH_ALLOW_LOCAL_HTTP.')
        forbidden = protected_paths(storage) if any(os.environ.get(k) for k in ('PROJECT2_TLS_CERT', 'PROJECT2_TLS_KEY')) else ()
        cert = tls_file('PROJECT2_TLS_CERT', forbidden)
        key = tls_file('PROJECT2_TLS_KEY', forbidden)
        if bool(cert) != bool(key) or (not loopback and not cert) or (cert and cert == key):
            raise ValueError('Для TLS потрібні окремі PROJECT2_TLS_CERT та PROJECT2_TLS_KEY у форматі PEM.')
        if name or cert:
            name = name or 'localhost'
            origin = f'https://{name}' + (f':{port}' if port != 443 else '')
            try:
                rp, origins = relying_party()
            except (ValueError, TypeError, AttributeError):
                raise ValueError('Перевірте PROJECT2_WEBAUTHN_RP_ID та PROJECT2_WEBAUTHN_ORIGINS.') from None
            if rp != name or origin not in origins:
                raise ValueError(f'PROJECT2_WEBAUTHN_RP_ID має бути {name}, а PROJECT2_WEBAUTHN_ORIGINS має містити {origin}.')
        networks = explicit_networks(os.environ.get('PROJECT2_ALLOWED_NETWORKS', 'auto').strip())
        trust = None
        if not loopback:
            ca = tls_file('PROJECT2_CLIENT_CA', forbidden)
            crl = tls_file('PROJECT2_CLIENT_CRL', forbidden)
            if not ca or not crl:
                raise ValueError('Для LAN обов’язкові PROJECT2_CLIENT_CA і PROJECT2_CLIENT_CRL. Підготуйте Device CA.')
            trust = DeviceTrust.read(ca, crl, cert)
            if trust.renewal_due:
                logger.warning(trust.summary())
        return cls(bind, loopback, port, name or 'localhost', cert, key, networks, trust)


class NetworkPolicy:
    def __init__(self, settings: NetworkSettings, *, discover: Callable = interface_networks,
                 clock: Callable = time.monotonic):
        self.settings = settings
        self._discover = discover
        self._clock = clock
        self._lock = Lock()
        self._next_refresh = float('-inf')
        self._cached = ()
        if not settings.loopback_only:
            self.allowed_networks()  # Initial discovery before accepting remote requests.

    def allowed_networks(self) -> tuple[Network, ...]:
        if self.settings.networks is not None:
            return self.settings.networks
        with self._lock:
            now = self._clock()
            if now >= self._next_refresh:
                try:
                    self._cached = self._discover()
                except (OSError, subprocess.SubprocessError, UnicodeError, psutil.Error):
                    self._cached = ()
                    logger.warning('Не вдалося прочитати мережеві інтерфейси. Доступний лише loopback.')
                self._next_refresh = now + 60
            return self._cached

    def allows(self, address: Address) -> bool:
        if address.is_loopback:
            return True
        if self.settings.loopback_only or address.is_unspecified or not address.is_private:
            return False
        return any(address in network for network in self.allowed_networks())
