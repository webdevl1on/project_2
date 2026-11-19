"""Verified device trust material for the direct Uvicorn listener."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import ssl

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization

PEM = serialization.Encoding.PEM
SCOPE_TRUST = 'project2.device_trust'


def single_pem(path, label, loader):
    data = path.read_bytes().strip()
    if (not data.startswith(b'-----BEGIN ' + label + b'-----')
            or not data.endswith(b'-----END ' + label + b'-----') or data.count(b'-----BEGIN ') != 1):
        raise ValueError(f'{path.name} має містити рівно один блок {label.decode()}.')
    return loader(data)


@dataclass(frozen=True)
class DeviceTrust:
    ca_file: Path
    crl_file: Path
    fingerprint: bytes
    crl_fingerprint: bytes
    next_update: datetime
    revoked: int

    @classmethod
    def read(cls, ca_file, crl_file, server_file):
        ca = single_pem(ca_file, b'CERTIFICATE', x509.load_pem_x509_certificate)
        crl = single_pem(crl_file, b'X509 CRL', x509.load_pem_x509_crl)
        now = datetime.now(UTC)
        try:
            constraints = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
            usage = ca.extensions.get_extension_for_class(x509.KeyUsage).value
            ca.verify_directly_issued_by(ca)
        except (x509.ExtensionNotFound, InvalidSignature, ValueError):
            raise ValueError('PROJECT2_CLIENT_CA має містити самопідписаний кореневий Device CA.') from None
        if not (constraints.ca and usage.key_cert_sign and usage.crl_sign
                and ca.not_valid_before_utc <= now < ca.not_valid_after_utc):
            raise ValueError('PROJECT2_CLIENT_CA потребує чинного CA з правом підпису сертифікатів і CRL.')
        server_chain = x509.load_pem_x509_certificates(server_file.read_bytes())
        for cert in server_chain:
            if cert.public_key() == ca.public_key():
                raise ValueError('Device CA має бути окремим від серверного CA.')
            try:
                cert.verify_directly_issued_by(ca)
            except (ValueError, InvalidSignature):
                continue
            raise ValueError('Device CA має бути окремим від серверного CA.')
        if crl.issuer != ca.subject or not crl.is_signature_valid(ca.public_key()):
            raise ValueError('PROJECT2_CLIENT_CRL має бути підписаний налаштованим Device CA.')
        if not crl.next_update_utc or not crl.last_update_utc <= now < crl.next_update_utc:
            raise ValueError('CRL нечинний. Поновіть: python -m app.security.device_ca crl --dir <каталог CA>')
        return cls(ca_file, crl_file, ca.fingerprint(hashes.SHA256()), crl.fingerprint(hashes.SHA256()),
                   crl.next_update_utc, len(crl))

    @property
    def renewal_due(self):
        return self.next_update - datetime.now(UTC) < timedelta(days=30)

    def days_left(self, now=None):
        # Whole days until nextUpdate; 0 on the last day, negative once expired.
        return (self.next_update - (now or datetime.now(UTC))).days

    def summary(self):
        return (f'mTLS: Device CA {self.fingerprint.hex()[:16]}, CRL до {self.next_update:%Y-%m-%d %H:%M UTC}, '
                f'відкликано {self.revoked}' + (' · Залишилося менше 30 днів, поновіть CRL до вказаної дати.'
                                                if self.renewal_due else ''))

    def ssl_context(self, config, default_factory):
        context = default_factory()
        # Uvicorn's server context has an empty trust store. Never inherit client roots.
        if any(context.cert_store_stats().values()):
            raise ValueError('Для mTLS потрібне окреме сховище довіри Device CA.')
        context.load_verify_locations(cafile=self.ca_file)
        context.load_verify_locations(cafile=self.crl_file)
        roots = context.get_ca_certs(binary_form=True)
        if (context.cert_store_stats() != {'x509': 1, 'x509_ca': 1, 'crl': 1} or len(roots) != 1
                or x509.load_der_x509_certificate(roots[0]).fingerprint(hashes.SHA256()) != self.fingerprint
                or single_pem(self.crl_file, b'X509 CRL', x509.load_pem_x509_crl).fingerprint(hashes.SHA256()) != self.crl_fingerprint):
            raise ValueError('Матеріали Device CA змінилися під час запуску. Повторіть запуск.')
        context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context

    def application(self, app):
        # Only the listener wired to this TLS factory supplies the in-process marker.
        # A generic ASGI server cannot serve LAN pages by passing HTTP headers.
        async def verified_listener(scope, receive, send):
            await app({**scope, SCOPE_TRUST: self}, receive, send)
        return verified_listener
