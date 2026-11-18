#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName='Set')]
param(
    [Parameter(ParameterSetName='Set', Mandatory)][Net.IPAddress]$IPAddress,
    [Parameter(ParameterSetName='Remove', Mandatory)][switch]$Remove,
    [string]$ServerName = 'foxlys.local'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
Assert-Project2ServerName $ServerName
$path = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
$bytes = [IO.File]::ReadAllBytes($path)
$updated = Update-Project2HostsBytes $bytes $ServerName $IPAddress -Remove:$Remove
if ([Collections.StructuralComparisons]::StructuralEqualityComparer.Equals($bytes, $updated)) {
    Write-Output 'Файл hosts уже має потрібний стан.'; return
}
if ($PSCmdlet.ShouldProcess($path, "Оновити позначений # project2 запис для $ServerName")) {
    Assert-Project2Administrator
    $temp = Join-Path (Split-Path -Parent $path) ([Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllBytes($temp, $updated)
        [IO.File]::Replace($temp, $path, [System.Management.Automation.Language.NullString]::Value)
    } finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }
    Write-Output 'Позначений запис hosts оновлено.'
}
