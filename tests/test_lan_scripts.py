"""Parse the Windows tools and exercise portable logic without changing the OS."""
from pathlib import Path
import shutil
import subprocess

import pytest

POWERSHELL = shutil.which('pwsh') or shutil.which('powershell')
pytestmark = pytest.mark.skipif(not POWERSHELL, reason='PowerShell parser is unavailable')
LAN = Path('scripts/lan').resolve()


def powershell(command):
    result = subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, (result.stderr + result.stdout).decode(errors='replace')


def test_all_lan_scripts_parse_and_windows_powershell_reads_ukrainian():
    scripts = [*LAN.glob('*.ps1'), *LAN.glob('*.psm1')]
    assert len(scripts) == 8 and all(p.read_bytes().startswith(b'\xef\xbb\xbf') for p in scripts)
    powershell('''
        $ErrorActionPreference = 'Stop'
        foreach ($script in Get-ChildItem scripts/lan -File) {
            $tokens = $null; $errors = $null
            [void][Management.Automation.Language.Parser]::ParseFile($script.FullName,[ref]$tokens,[ref]$errors)
            if ($errors.Count) { throw "$($script.Name): $errors" }
        }
    ''')


def test_hosts_set_remove_and_repeat_preserve_unmanaged_lines_encoding_and_line_ends():
    powershell(r'''
        $ErrorActionPreference = 'Stop'
        Import-Module ./scripts/lan/Project2Lan.psm1
        $encodings = @([Text.Encoding]::UTF8,[Text.Encoding]::Unicode,[Text.Encoding]::GetEncoding(28591))
        foreach ($enc in $encodings) {
            $previous = "# André`r`n192.168.3.2 other.local # project2`n"
            $managed = "10.0.0.7 foxlys.local # project2`r`n"
            $end = '# unrelated last line'
            $bytes = [byte[]]($enc.GetPreamble() + $enc.GetBytes($previous + $managed + $managed + $end))
            $updated = Update-Project2HostsBytes $bytes 'foxlys.local' '192.168.0.9'
            $expected = $previous + "192.168.0.9 foxlys.local # project2`r`n" + $end
            $eq = [Collections.StructuralComparisons]::StructuralEqualityComparer
            if (-not $eq.Equals($updated, [byte[]]($enc.GetPreamble() + $enc.GetBytes($expected)))) { throw 'replace' }
            $repeat = Update-Project2HostsBytes $updated 'foxlys.local' '192.168.0.9'
            if (-not $eq.Equals($updated,$repeat)) { throw 'repeat' }
            $clean = Update-Project2HostsBytes $updated 'foxlys.local' $null -Remove
            if (-not $eq.Equals($clean, [byte[]]($enc.GetPreamble() + $enc.GetBytes($previous + $end)))) { throw 'remove' }
            $append = Update-Project2HostsBytes $clean 'foxlys.local' '10.0.0.7'
            $expected = $previous + $end + "`r`n" + $managed
            if (-not $eq.Equals($append, [byte[]]($enc.GetPreamble() + $enc.GetBytes($expected)))) { throw 'append' }
        }
    ''')


def test_ca_name_constraints_extension_limits_trust_to_lan_server():
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    result = subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', '''
        $ErrorActionPreference = 'Stop'
        Import-Module ./scripts/lan/Project2Lan.psm1
        $ext = New-Project2NameConstraints 'foxlys.local'
        if (-not $ext.Critical -or $ext.Oid.Value -ne '2.5.29.30') { throw 'extension' }
        [BitConverter]::ToString($ext.RawData).Replace('-', '')
    '''], capture_output=True, timeout=30)
    assert result.returncode == 0, (result.stderr + result.stdout).decode(errors='replace')
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    import datetime
    raw = bytes.fromhex(result.stdout.decode().strip())
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'probe')])
    now = datetime.datetime.now(datetime.UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier('2.5.29.30'), raw), critical=True)
            .sign(key, hashes.SHA256()))
    value = x509.load_der_x509_certificate(cert.public_bytes(serialization.Encoding.DER)).extensions.get_extension_for_class(x509.NameConstraints).value
    assert [n.value for n in value.permitted_subtrees if isinstance(n, x509.DNSName)] == ['foxlys.local', 'localhost']
    assert [n.value.rfc4514_string() for n in value.permitted_subtrees if isinstance(n, x509.DirectoryName)] == ['CN=foxlys.local']
    assert sorted(str(n.value) for n in value.excluded_subtrees) == ['0.0.0.0/0', '::/0']
