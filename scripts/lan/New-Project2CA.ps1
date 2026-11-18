#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ServerName = 'foxlys.local',
    [string]$EnvFile,
    [string]$TlsDirectory = (Join-Path $env:SystemDrive 'project2-secrets\tls'),
    # Fallback only if a client cannot validate the name-constrained chain.
    [switch]$NoNameConstraints
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
Assert-Project2ServerName $ServerName
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$directory = Get-Project2ExternalPath $TlsDirectory $repo
Assert-Project2TlsDirectory $directory $repo $EnvFile
$files = @('project2-ca.pfx', 'project2-ca.cer', 'server.crt.pem', 'server.key.pem')
$present = @($files | Where-Object { Test-Path -LiteralPath (Join-Path $directory $_) })
if ($present.Count -and $present.Count -ne $files.Count) {
    throw 'Каталог містить неповний комплект. Збережіть файли та перевірте їх перед повторним запуском.'
}
if (-not $PSCmdlet.ShouldProcess($directory, 'Захистити каталог і підготувати CA та серверну пару TLS')) { return }
Set-Project2PrivateDirectory $directory @('project2-ca.pfx','project2-ca.cer','server.crt.pem','server.key.pem')
if ($present.Count -eq $files.Count) {
    $existing = Get-Project2CA (Join-Path $directory 'project2-ca.cer')
    Write-Output "Комплект уже існує. SHA-256 CA: $(Get-Project2Fingerprint $existing)"
    return
}
$password = Read-Host 'Введіть пароль для захищеного PFX кореневого CA' -AsSecureString
if (-not $password.Length) { throw 'Пароль PFX обовʼязковий.' }
$stage = Join-Path $directory ([Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($stage) | Out-Null
$published = [Collections.Generic.List[string]]::new()
try {
    $now = Get-Date
    $options = @{
        Type = 'Custom'; Subject = 'CN=Project 2 Local CA'; CertStoreLocation = 'Cert:\CurrentUser\My'
        KeyAlgorithm = 'RSA'; KeyLength = 3072; Provider = 'Microsoft Software Key Storage Provider'
        KeyExportPolicy = 'ExportableEncrypted'; HashAlgorithm = 'SHA256'; KeyUsage = @('CertSign','CRLSign')
        NotBefore = $now.AddMinutes(-5); NotAfter = $now.AddMinutes(-5).AddYears(10)
        TextExtension = @('2.5.29.19={critical}{text}ca=1&pathlength=0')
    }
    if (-not $NoNameConstraints) { $options.Extension = @(New-Project2NameConstraints $ServerName) }
    else { Write-Warning 'CA створюється без обмеження імен: його ключ зможе підписати будь-який сайт для ПК, які довіряють цьому CA.' }
    $ca = New-SelfSignedCertificate @options
    try {
        Export-Certificate -Cert $ca -FilePath (Join-Path $stage 'project2-ca.cer') -Type CERT | Out-Null
        Export-PfxCertificate -Cert $ca -FilePath (Join-Path $stage 'project2-ca.pfx') -Password $password -CryptoAlgorithmOption AES256_SHA256 -ChainOption EndEntityCertOnly | Out-Null
        New-Project2Leaf $ca $ServerName $stage
        $fingerprint = Get-Project2Fingerprint $ca
    } finally { Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($ca.Thumbprint)" -DeleteKey -Force }
    foreach ($name in $files) {
        $target = Join-Path $directory $name
        [IO.File]::Move((Join-Path $stage $name), $target)
        $published.Add($target)
    }
    Write-Output "Готово. Для клієнтів передайте project2-ca.cer. SHA-256 CA: $fingerprint"
} catch {
    foreach ($path in $published) { [IO.File]::Delete($path) }
    throw
} finally {
    $password.Dispose()
    [IO.Directory]::Delete($stage, $true)
}
