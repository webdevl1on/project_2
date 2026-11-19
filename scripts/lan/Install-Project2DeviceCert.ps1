#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param([Parameter(Mandatory)][string]$PfxPath, [string]$ExpectedSha256)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
$path = (Resolve-Path -LiteralPath $PfxPath).ProviderPath
if ([IO.Path]::GetExtension($path) -ne '.pfx') { throw 'Виберіть файл сертифіката з розширенням .pfx.' }
$password = Read-Host 'Пароль PFX пристрою' -AsSecureString
try {
    # Hold the selected PFX read-only through inspection and import.
    $file = [IO.File]::Open($path, 'Open', 'Read', 'Read')
    try {
        $sourceHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        $data = Get-PfxData -FilePath $path -Password $password
        $leaves = @($data.EndEntityCertificates | Where-Object { $_ })
        if ($leaves.Count -ne 1 -or @($data.OtherCertificates | Where-Object { $_ }).Count -gt 0) {
            throw 'PFX має містити лише один сертифікат пристрою без CA.'
        }
        $cert = $leaves[0]
        if (-not (Test-Project2DeviceCertificate $cert -Current)) { throw 'Потрібен чинний сертифікат Project 2 Devices з clientAuth.' }
        $sha = Get-Project2Fingerprint $cert
        Write-Output "Пристрій $($cert.GetNameInfo('SimpleName',$false)), чинний до $($cert.NotAfter), SHA-256 $sha"
        if ($ExpectedSha256 -and ($ExpectedSha256 -replace '[: ]','') -ne $sha) { throw 'Відбиток сертифіката відрізняється від очікуваного.' }
        $known = @(Get-ChildItem Cert:\CurrentUser\My | Where-Object {
            $_.HasPrivateKey -and (Test-Project2DeviceCertificate $_ -Current) -and
                [Convert]::ToBase64String($_.Extensions['2.5.29.35'].RawData) -eq [Convert]::ToBase64String($cert.Extensions['2.5.29.35'].RawData)
        })
        if ($known.Count -and $cert.Thumbprint -notin $known.Thumbprint) {
            Write-Warning 'У цього користувача вже є чинний сертифікат того самого Device CA. Для заміни видаліть попередній через Remove-Project2DeviceCert.ps1.'
            return
        }
        if ($known.Count) {
            $matching = $known | Where-Object Thumbprint -eq $cert.Thumbprint | Select-Object -First 1
            Assert-Project2DeviceKey $matching
            Write-Output 'Цей сертифікат уже встановлений.'
        }
        else {
            if (-not $PSCmdlet.ShouldProcess("CurrentUser\My, SHA-256 $sha", 'Імпортувати сертифікат із неекспортованим ключем')) { return }
            $target = "Cert:\CurrentUser\My\$($cert.Thumbprint)"
            $alreadyPresent = Test-Path -LiteralPath $target
            try {
                $installed = Import-PfxCertificate -FilePath $path -Password $password -CertStoreLocation Cert:\CurrentUser\My
                if (-not $installed.HasPrivateKey -or (Get-Project2Fingerprint $installed) -ne $sha) { throw 'Не вдалося підтвердити імпорт сертифіката з ключем.' }
                Assert-Project2DeviceKey $installed
            } catch {
                if (-not $alreadyPresent -and (Test-Path -LiteralPath $target)) {
                    $partial = Get-Item -LiteralPath $target
                    Remove-Item -LiteralPath $target -DeleteKey:$partial.HasPrivateKey -Force
                }
                throw
            }
            Write-Output 'Сертифікат встановлено для поточного користувача Windows.'
        }
    } finally { $file.Dispose() }
} finally { $password.Dispose() }
if ($PSCmdlet.ShouldProcess($path, 'Видалити перенесений PFX') -and
    $PSCmdlet.ShouldContinue("Видалити $path після успішного імпорту?", 'Видалення PFX')) {
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $sourceHash) { throw 'Файл змінився після імпорту. Видалення зупинено.' }
    Remove-Item -LiteralPath $path -Force
}
