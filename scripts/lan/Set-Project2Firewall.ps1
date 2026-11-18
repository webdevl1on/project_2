#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param([ValidateRange(1,65535)][int]$Port, [string]$EnvFile = (Join-Path $PSScriptRoot '..\..\.env'))
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
$Port = Get-Project2Port $Port $EnvFile
Assert-Project2Administrator
foreach ($profile in @(Get-NetConnectionProfile | Where-Object NetworkCategory -eq Public)) {
    Write-Warning "Інтерфейс $($profile.InterfaceAlias) має профіль Public. Для довіреної LAN: Set-NetConnectionProfile -InterfaceIndex $($profile.InterfaceIndex) -NetworkCategory Private"
}
$name = 'Project2-LAN-HTTPS'
$rule = Get-NetFirewallRule -PolicyStore PersistentStore -Name $name -ErrorAction SilentlyContinue
if ($PSCmdlet.ShouldProcess("Private, TCP $Port", 'Налаштувати вхідне правило Project 2')) {
    $settings = @{ Direction='Inbound'; Action='Allow'; Enabled='True'; Profile='Private'; EdgeTraversalPolicy='Block'; RemoteAddress='LocalSubnet' }
    if ($null -eq $rule) {
        New-NetFirewallRule @settings -Name $name -DisplayName 'Project 2 LAN HTTPS' -Protocol TCP -LocalPort $Port -PolicyStore PersistentStore | Out-Null
    } else {
        Set-NetFirewallRule @settings -Name $name -PolicyStore PersistentStore | Out-Null
        $rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $Port | Out-Null
    }
    Write-Output "Правило $name налаштовано для TCP $Port у профілі Private, лише з локальної підмережі."
}
# Inspect effective rules by protocol/port, independent of the Windows display language.
$mdns = Get-NetFirewallRule -PolicyStore ActiveStore -Enabled True -Direction Inbound -Action Allow |
    Where-Object { $_.Profile -eq 'Any' -or ($_.Profile.ToString() -split ',\s*') -contains 'Private' } |
    Get-NetFirewallPortFilter | Where-Object { $_.Protocol -in @('UDP', '17') -and $_.LocalPort -contains '5353' } |
    Select-Object -First 1
if ($mdns) { Write-Output 'mDNS: є активне вхідне правило UDP 5353 для Private.' }
else { Write-Warning 'mDNS: увімкніть правило Windows mDNS (UDP 5353) для Private або застосуйте Add-Project2HostsEntry.ps1 на клієнті.' }
