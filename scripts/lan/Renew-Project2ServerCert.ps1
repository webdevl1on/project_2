#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ServerName = 'foxlys.local',
    [string]$EnvFile,
    [string]$TlsDirectory = (Join-Path $env:SystemDrive 'project2-secrets\tls'),
    [ValidateRange(1,824)][int]$RenewBeforeDays = 30,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
Assert-Project2ServerName $ServerName
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$directory = Get-Project2ExternalPath $TlsDirectory $repo
Assert-Project2TlsDirectory $directory $repo $EnvFile
$ca = Get-Project2CA (Join-Path $directory 'project2-ca.cer')
$certPath = Join-Path $directory 'server.crt.pem'
$keyPath = Join-Path $directory 'server.key.pem'
$pfx = Join-Path $directory 'project2-ca.pfx'
$body = [IO.File]::ReadAllText($certPath).Replace('-----BEGIN CERTIFICATE-----','').Replace('-----END CERTIFICATE-----','')
$current = [Security.Cryptography.X509Certificates.X509Certificate2]::new([Convert]::FromBase64String($body))
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw 'Не знайдено серверний ключ.' }
if (-not $Force -and $current.GetNameInfo('DnsName',$false) -eq $ServerName -and $current.NotAfter -gt (Get-Date).AddDays($RenewBeforeDays)) {
    Write-Output "Сертифікат $ServerName чинний до $($current.NotAfter). Перевипуск поки не потрібний."
    return
}
if (-not $PSCmdlet.ShouldProcess($ServerName, 'Перевипустити серверну пару чинним CA')) { return }
Set-Project2PrivateDirectory $directory @('project2-ca.pfx','project2-ca.cer','server.crt.pem','server.key.pem')
$password = Read-Host 'Введіть пароль PFX чинного CA' -AsSecureString
$stage = Join-Path $directory ([Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($stage) | Out-Null
$keepStage = $false
try {
    $data = Get-PfxData -FilePath $pfx -Password $password
    $contents = @(@($data.EndEntityCertificates) + @($data.OtherCertificates) | Where-Object { $null -ne $_ })
    if ($contents.Count -ne 1 -or $contents[0].Thumbprint -ne $ca.Thumbprint) { throw 'PFX не відповідає публічному CA.' }
    $tempCert = "Cert:\CurrentUser\My\$($ca.Thumbprint)"
    if (Test-Path -LiteralPath $tempCert) { throw 'CA вже є в CurrentUser\My. Перевірте залишок попередньої операції.' }
    try {
        $signer = Import-PfxCertificate -FilePath $pfx -Password $password -CertStoreLocation Cert:\CurrentUser\My
        New-Project2Leaf $signer $ServerName $stage
    } finally {
        if (Test-Path -LiteralPath $tempCert) { Remove-Item -LiteralPath $tempCert -DeleteKey -Force }
    }
    $previous = Join-Path $stage 'previous.key.pem'
    [IO.File]::Replace((Join-Path $stage 'server.key.pem'), $keyPath, $previous)
    try { [IO.File]::Replace((Join-Path $stage 'server.crt.pem'), $certPath, (Join-Path $stage 'previous.crt.pem')) }
    catch {
        $keepStage = $true
        [IO.File]::Replace($previous, $keyPath, (Join-Path $stage 'unused.key.pem'))
        $keepStage = $false
        throw
    }
    Write-Output "Сертифікат перевипущено тим самим CA. Перезапустіть завдання сервера. SHA-256 CA: $(Get-Project2Fingerprint $ca)"
} finally {
    $password.Dispose()
    if ($keepStage) { Write-Warning "Перевірте пару TLS та захищені файли відновлення у $stage." }
    else { [IO.Directory]::Delete($stage, $true) }
}
