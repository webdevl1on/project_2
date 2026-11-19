#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param()
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
$certs = @(Get-ChildItem Cert:\CurrentUser\My | Where-Object { Test-Project2DeviceCertificate $_ })
if (-not $certs.Count) { Write-Output 'Сертифікати пристроїв Project 2 відсутні.'; return }
foreach ($cert in $certs) {
    $label = "$($cert.Subject), до $($cert.NotAfter), SHA-256 $(Get-Project2Fingerprint $cert)"
    if ($PSCmdlet.ShouldProcess($label, 'Видалити сертифікат пристрою та його приватний ключ')) {
        Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($cert.Thumbprint)" -DeleteKey:$cert.HasPrivateKey -Force
        Write-Output "Видалено $label"
    }
}
