#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param([Parameter(Mandatory)][string]$CertificatePath, [string]$ExpectedSha256)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
$path = (Resolve-Path -LiteralPath $CertificatePath).ProviderPath
$ca = Get-Project2CA $path
$fingerprint = Get-Project2Fingerprint $ca
Write-Output "CA $($ca.Subject), чинний до $($ca.NotAfter). SHA-256: $fingerprint"
if ($ExpectedSha256 -and $ExpectedSha256.Replace(':','').Replace(' ','') -ne $fingerprint) { throw 'Відбиток відрізняється від переданого адміністратором.' }
if (Test-Path -LiteralPath "Cert:\LocalMachine\Root\$($ca.Thumbprint)") { Write-Output 'Цей CA уже встановлений.'; return }
if ($PSCmdlet.ShouldProcess("LocalMachine\Root, SHA-256 $fingerprint", 'Після звірки відбитка довіряти цьому кореневому CA')) {
    Assert-Project2Administrator
    # Install the exact bytes whose fingerprint the operator confirmed.
    $store = [Security.Cryptography.X509Certificates.X509Store]::new('Root','LocalMachine')
    try { $store.Open('ReadWrite'); $store.Add($ca) } finally { $store.Close() }
    Write-Output 'Довіру до CA встановлено.'
}
