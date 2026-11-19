# Windows PowerShell 5.1 / .NET Framework. Shared PKI and deployment helpers.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Assert-Project2Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Запустіть Windows PowerShell від імені адміністратора.'
    }
}

function Assert-Project2ServerName([string]$Name) {
    if ($Name.Length -gt 253 -or $Name -notmatch '^(?![\d.]+$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$' -or $Name -eq 'localhost') {
        throw 'Вкажіть DNS-імʼя LAN-сервера, наприклад foxlys.local.'
    }
}

function Get-Project2ExternalPath([string]$Path, [string]$RepoRoot) {
    $full = [IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)).TrimEnd('\')
    $repo = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
    if ($full -eq [IO.Path]::GetPathRoot($full).TrimEnd('\') -or $full -eq $repo -or
        $full.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $repo.StartsWith($full + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Виберіть окремий каталог поза репозиторієм і його батьківськими каталогами.'
    }
    for ($part = [IO.DirectoryInfo]::new($full); $null -ne $part; $part = $part.Parent) {
        if ((Test-Path -LiteralPath $part.FullName) -and ((Get-Item -Force -LiteralPath $part.FullName).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Шлях містить посилання або junction. Виберіть фізичний каталог.'
        }
    }
    return $full
}

function Get-Project2EnvValue([string]$Name, [string]$EnvFile) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ($null -ne $value) { return $value }
    if ($EnvFile -and [IO.File]::Exists($EnvFile)) {
        $pattern = '^\s*(?:export\s+)?' + [regex]::Escape($Name) + '\s*=\s*(.*)$'
        foreach ($line in [IO.File]::ReadAllLines($EnvFile)) {
            if ($line -cmatch $pattern) {
                $value = $Matches[1].Trim()
                if ($value -match '^(["''])(.*?)\1\s*(?:#.*)?$') { $value = $Matches[2] }
                else { $value = ($value -replace '\s+#.*$', '').Trim() }
            }
        }
    }
    return $value
}

function Assert-Project2TlsDirectory([string]$Directory, [string]$RepoRoot, [string]$EnvFile) {
    if (-not $EnvFile) { $EnvFile = $env:PROJECT2_ENV_FILE }
    if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot '.env' }
    $roots = @(foreach ($key in 'DOCUMENT', 'PHOTO', 'TEMP', 'EXPORT', 'BACKUP') {
        Get-Project2EnvValue "PROJECT2_${key}_STORAGE" $EnvFile
    })
    $backup = Get-Project2EnvValue 'PROJECT2_BACKUP_CONFIG' $EnvFile
    if ($backup) {
        if (-not [IO.Path]::IsPathRooted($backup)) { $backup = Join-Path $RepoRoot $backup }
        $config = [IO.File]::ReadAllText($backup) | ConvertFrom-Json
        $roots += @($config.PSObject.Properties | Where-Object Name -in @('secrets','staging','external','drill_root','emergency_root') | ForEach-Object { $_.Value })
    }
    foreach ($root in $roots) {
        if (-not $root) { continue }
        if ($root.Contains('${')) { throw 'Для перевірки шляху TLS задайте розгорнуті шляхи сховищ у середовищі.' }
        if (-not [IO.Path]::IsPathRooted($root)) { $root = Join-Path $RepoRoot $root }
        $root = [IO.Path]::GetFullPath($root).TrimEnd('\')
        if ($Directory -eq $root -or $Directory.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase) -or
            $root.StartsWith($Directory + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Каталоги TLS і даних мають бути окремими.' }
    }
}

function Set-Project2PrivateDirectory([string]$Path, [string[]]$FileNames, [Security.Principal.SecurityIdentifier]$Writer) {
    if ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($Path)).DriveFormat -ne 'NTFS') { throw 'Для захищеного каталогу потрібен том NTFS.' }
    if ([IO.Directory]::Exists($Path)) {
        foreach ($entry in Get-ChildItem -Force -LiteralPath $Path) {
            if ($entry.Name -notin $FileNames -or $entry.PSIsContainer -or ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'Для зміни ACL виберіть окремий каталог лише з файлами цієї операції.'
            }
        }
    }
    [IO.Directory]::CreateDirectory($Path) | Out-Null
    $owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $security = [Security.AccessControl.DirectorySecurity]::new()
    $security.SetOwner($owner)
    $security.SetAccessRuleProtection($true, $false)
    $inherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    foreach ($sid in @($owner.Value, 'S-1-5-18', 'S-1-5-32-544') | Select-Object -Unique) {
        $security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid), 'FullControl', $inherit, 'None', 'Allow'))
    }
    if ($Writer -and $Writer -ne $owner) {
        $security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($Writer, 'Modify', $inherit, 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $Path -AclObject $security
    $trusted = @($owner.Value, 'S-1-5-18', 'S-1-5-32-544')
    if ($Writer) { $trusted += $Writer.Value }
    foreach ($file in Get-ChildItem -Force -LiteralPath $Path) {
        $acl = Get-Acl -LiteralPath $file.FullName
        $rules = $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])
        if ($rules | Where-Object { $_.AccessControlType -eq 'Allow' -and $_.IdentityReference.Value -notin $trusted }) {
            throw 'Наявний файл має окремі сторонні дозволи. Перевірте його NTFS ACL.'
        }
    }
}

function Get-Project2Fingerprint([Security.Cryptography.X509Certificates.X509Certificate2]$Certificate) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($Certificate.RawData)).Replace('-', '') }
    finally { $hash.Dispose() }
}

function Get-Project2CA([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $type = [Security.Cryptography.X509Certificates.X509Certificate2]::GetCertContentType($bytes)
    if ($type -ne 'Cert') { throw 'Потрібен публічний кореневий сертифікат .cer.' }
    $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new($bytes)
    $ca = $cert.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.19' }
    $usage = $cert.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.15' }
    if (-not $ca -or -not $ca.CertificateAuthority -or -not $usage -or
        -not ($usage.KeyUsages -band [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyCertSign) -or
        $cert.HasPrivateKey -or $cert.Subject -ne $cert.Issuer -or $cert.NotAfter -le (Get-Date) -or $cert.NotBefore -gt (Get-Date)) {
        throw 'Файл не містить чинного публічного кореневого CA з правом підпису сертифікатів.'
    }
    return $cert
}

function Write-Project2Pem([string]$Path, [string]$Label, [byte[]]$Bytes) {
    $lines = [regex]::Matches([Convert]::ToBase64String($Bytes), '.{1,64}')
    $body = ($lines | ForEach-Object { $_.Value }) -join "`r`n"
    [IO.File]::WriteAllText($Path, "-----BEGIN $Label-----`r`n$body`r`n-----END $Label-----`r`n", [Text.Encoding]::ASCII)
}

function ConvertTo-Project2Der([byte]$Tag, [byte[]]$Content) {
    # Minimal DER TLV encoder (definite length) for the Name Constraints extension.
    if ($null -eq $Content) { $Content = [byte[]]@() }
    $length = $Content.Length
    if ($length -lt 0x80) { $prefix = [byte[]]@($Tag, $length) }
    else {
        $digits = [Collections.Generic.List[byte]]::new()
        for ($n = $length; $n -gt 0; $n = $n -shr 8) { $digits.Insert(0, [byte]($n -band 0xFF)) }
        $prefix = [byte[]](@($Tag, (0x80 -bor $digits.Count)) + $digits.ToArray())
    }
    return ,([byte[]]($prefix + $Content))
}

function New-Project2NameConstraints([string]$ServerName) {
    # RFC 5280 NameConstraints, critical. The root CA may only sign the LAN server:
    # permitted dNSName ServerName/localhost and directoryName CN=ServerName (Windows
    # treats a name form without any constraint as undefined); all IPv4/IPv6 excluded.
    $permitted = [byte[]]@()
    foreach ($dns in @($ServerName, 'localhost')) {
        $permitted += ConvertTo-Project2Der 0x30 (ConvertTo-Project2Der 0x82 ([Text.Encoding]::ASCII.GetBytes($dns)))
    }
    $subject = [Security.Cryptography.X509Certificates.X500DistinguishedName]::new("CN=$ServerName").RawData
    $permitted += ConvertTo-Project2Der 0x30 (ConvertTo-Project2Der 0xA4 $subject)
    $excluded = [byte[]]@()
    foreach ($size in 8, 32) {
        $excluded += ConvertTo-Project2Der 0x30 (ConvertTo-Project2Der 0x87 ([byte[]]::new($size)))
    }
    $body = [byte[]]((ConvertTo-Project2Der 0xA0 $permitted) + (ConvertTo-Project2Der 0xA1 $excluded))
    return [Security.Cryptography.X509Certificates.X509Extension]::new('2.5.29.30', (ConvertTo-Project2Der 0x30 $body), $true)
}

function New-Project2Leaf($Signer, [string]$ServerName, [string]$Stage) {
    $now = Get-Date
    $end = $now.AddDays(824)
    if ($Signer.NotAfter -lt $end) { $end = $Signer.NotAfter }
    if ($end -le $now) { throw 'Строк дії CA завершився.' }
    $options = @{
        Type = 'Custom'; Subject = "CN=$ServerName"; DnsName = @($ServerName, 'localhost'); Signer = $Signer
        Provider = 'Microsoft Software Key Storage Provider'; KeyAlgorithm = 'RSA'; KeyLength = 3072
        KeyExportPolicy = 'Exportable'; HashAlgorithm = 'SHA256'; CertStoreLocation = 'Cert:\CurrentUser\My'
        KeyUsage = @('DigitalSignature', 'KeyEncipherment'); NotBefore = $now.AddMinutes(-5); NotAfter = $end
        TextExtension = @('2.5.29.19={critical}{text}ca=0', '2.5.29.37={text}1.3.6.1.5.5.7.3.1')
    }
    $leaf = New-SelfSignedCertificate @options
    try {
        Write-Project2Pem (Join-Path $Stage 'server.crt.pem') 'CERTIFICATE' $leaf.RawData
        $rsa = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($leaf)
        try {
            $bytes = $rsa.Key.Export([Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob)
            try { Write-Project2Pem (Join-Path $Stage 'server.key.pem') 'PRIVATE KEY' $bytes }
            finally { [Array]::Clear($bytes, 0, $bytes.Length) }
        } finally { $rsa.Dispose() }
    } finally { Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($leaf.Thumbprint)" -DeleteKey -Force }
}

function Get-Project2Port([int]$Port, [string]$EnvFile) {
    if (-not $Port) {
        $value = Get-Project2EnvValue 'PROJECT2_PORT' $EnvFile
        if ($value) { $Port = [int]$value } else { $Port = 8443 }
    }
    if ($Port -lt 1 -or $Port -gt 65535) { throw 'Некоректний TCP-порт.' }
    return $Port
}

function Update-Project2HostsBytes([byte[]]$Bytes, [string]$ServerName, [Net.IPAddress]$IPAddress, [switch]$Remove) {
    # ISO-8859-1 round-trips all bytes in BOM-less ANSI/UTF-8 hosts files. Preserve BOM and EOLs.
    $encoding = [Text.Encoding]::GetEncoding(28591)
    foreach ($candidate in @([Text.Encoding]::UTF32, [Text.Encoding]::Unicode, [Text.Encoding]::BigEndianUnicode, [Text.Encoding]::UTF8)) {
        $prefix = $candidate.GetPreamble()
        if ($prefix.Length -and $bytes.Length -ge $prefix.Length -and
            [BitConverter]::ToString($bytes, 0, $prefix.Length) -eq [BitConverter]::ToString($prefix)) {
            $encoding = $candidate; break
        }
    }
    $preamble = $encoding.GetPreamble()
    $text = $encoding.GetString($bytes, $preamble.Length, $bytes.Length - $preamble.Length)
    $pattern = '^\s*[0-9A-Fa-f:.%]+[ \t]+' + [regex]::Escape($ServerName) + '[ \t]+#[ \t]*project2[ \t]*$'
    $eol = if ($text.Contains("`r`n")) { "`r`n" } elseif ($text.Contains("`n")) { "`n" } else { "`r`n" }
    $outputText = [Text.StringBuilder]::new()
    $found = $false
    foreach ($line in [regex]::Matches($text, '([^\r\n]*)(\r\n|\n|\r|$)')) {
        $body = $line.Groups[1].Value
        if ($body -match $pattern) {
            if (-not $found -and -not $Remove) { [void]$outputText.Append("$IPAddress $ServerName # project2" + $line.Groups[2].Value) }
            $found = $true
        } else { [void]$outputText.Append($line.Value) }
    }
    if (-not $found -and -not $Remove) {
        if ($text.Length -and $text -notmatch '[\r\n]$') { [void]$outputText.Append($eol) }
        [void]$outputText.Append("$IPAddress $ServerName # project2" + $eol)
    }
    return ,([byte[]]($preamble + $encoding.GetBytes($outputText.ToString())))
}

function Test-Project2DeviceCertificate($Certificate, [switch]$Current) {
    if ($Certificate.Issuer -ne 'CN=Project 2 Device CA') { return $false }
    $parts = $Certificate.SubjectName.Decode([Security.Cryptography.X509Certificates.X500DistinguishedNameFlags]::UseNewLines) -split '\r?\n'
    if ('O=Project 2 Devices' -notin $parts -or $Certificate.GetNameInfo('SimpleName', $false) -cnotmatch '^[a-z0-9-]{1,40}$') { return $false }
    $eku = $Certificate.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.37' }
    $usage = $Certificate.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.15' }
    $basic = $Certificate.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.19' }
    $aki = $Certificate.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.35' }
    if (-not $aki -or -not $basic -or $basic.CertificateAuthority -or -not $eku -or -not $usage -or
        -not ($usage.KeyUsages -band [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature) -or
        '1.3.6.1.5.5.7.3.2' -notin @($eku.EnhancedKeyUsages | ForEach-Object { $_.Value })) { return $false }
    $now = Get-Date
    return (-not $Current -or ($Certificate.NotBefore -le $now -and $now -lt $Certificate.NotAfter))
}

function Assert-Project2DeviceKey($Certificate) {
    $key = [Security.Cryptography.X509Certificates.ECDsaCertificateExtensions]::GetECDsaPrivateKey($Certificate)
    if ($null -eq $key) { throw 'Приватний ключ пристрою недоступний цьому користувачу Windows.' }
    try {
        if ($key -isnot [Security.Cryptography.ECDsaCng] -or
            $key.Key.ExportPolicy -ne [Security.Cryptography.CngExportPolicies]::None) {
            throw 'Політика ключа допускає експорт або не підтверджена. Перевірте ключ і повторіть імпорт без дозволу експорту.'
        }
    } finally { $key.Dispose() }
}

Export-ModuleMember -Function Assert-Project2Administrator, Assert-Project2ServerName, Get-Project2ExternalPath, Assert-Project2TlsDirectory, Set-Project2PrivateDirectory, Get-Project2Fingerprint, Get-Project2CA, ConvertTo-Project2Der, New-Project2NameConstraints, New-Project2Leaf, Get-Project2Port, Update-Project2HostsBytes, Test-Project2DeviceCertificate, Assert-Project2DeviceKey
