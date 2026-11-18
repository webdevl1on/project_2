#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName='Register')]
param(
    [Parameter(ParameterSetName='Register', Mandatory)][string]$UserName,
    [Parameter(ParameterSetName='Register')][PSCredential]$Credential,
    [Parameter(ParameterSetName='Register')][string]$RepoRoot = (Join-Path $PSScriptRoot '..\..'),
    [Parameter(ParameterSetName='Register')][string]$EnvFile,
    [Parameter(ParameterSetName='Register')][string]$LogDirectory = (Join-Path $env:ProgramData 'Project2\LanLogs'),
    [Parameter(ParameterSetName='Unregister', Mandatory)][switch]$Unregister,
    [Parameter(ParameterSetName='Status', Mandatory)][switch]$Status,
    [string]$TaskName = 'Project2-LAN'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
$description = 'Project 2 LAN: HTTPS (app.serve)'
$task = Get-ScheduledTask -TaskPath '\' -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Status) {
    if (-not $task) { Write-Output 'Завдання не зареєстровано.'; return }
    $result = $task | Get-ScheduledTaskInfo
    [pscustomobject]@{ Завдання=$task.TaskName; Стан=$task.State; Акаунт=$task.Principal.UserId; ОстаннійЗапуск=$result.LastRunTime; КодРезультату=$result.LastTaskResult }
    return
}
if ($task -and $task.Description -ne $description) { throw 'Імʼя вже належить іншому завданню.' }
if ($Unregister) {
    if ($task -and $PSCmdlet.ShouldProcess($TaskName, 'Зняти реєстрацію завдання Project 2')) {
        Assert-Project2Administrator
        Unregister-ScheduledTask -TaskPath '\' -TaskName $TaskName -Confirm:$false
    }
    return
}
$repo = (Resolve-Path -LiteralPath $RepoRoot).ProviderPath
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'У репозиторії немає .venv\Scripts\python.exe.' }
if (-not $EnvFile) { $EnvFile = Join-Path $repo '.env' }
$envPath = (Resolve-Path -LiteralPath $EnvFile).ProviderPath
$logDir = Get-Project2ExternalPath $LogDirectory $repo
$log = Join-Path $logDir 'server.log'
if (($envPath + $log) -match '["\r\n]') { throw 'Неприпустимий шлях до конфігурації або журналу.' }
$arguments = '-m app.serve --env-file "{0}" --log-file "{1}"' -f $envPath,$log
function Get-AccountSid([string]$Account) {
    if ($Account -match '^S-1-') { return [Security.Principal.SecurityIdentifier]::new($Account) }
    return [Security.Principal.NTAccount]::new($Account).Translate([Security.Principal.SecurityIdentifier])
}
$sid = Get-AccountSid $UserName
if ($sid.IsWellKnown([Security.Principal.WellKnownSidType]::LocalSystemSid)) { throw 'Вкажіть окремий обліковий запис Windows для завдання.' }
if ($task -and $task.Settings.Enabled -and $task.Actions.Count -eq 1 -and
    $task.Actions[0].Execute -eq $python -and $task.Actions[0].Arguments -ceq $arguments -and $task.Actions[0].WorkingDirectory -eq $repo -and
    (Get-AccountSid $task.Principal.UserId) -eq $sid -and $task.Principal.LogonType -eq 'Password' -and $task.Principal.RunLevel -eq 'Limited' -and
    $task.Triggers.Count -eq 1 -and $task.Triggers[0].Enabled -and $task.Triggers[0].CimClass.CimClassName -eq 'MSFT_TaskBootTrigger' -and
    $task.Settings.StartWhenAvailable -and $task.Settings.MultipleInstances -eq 'IgnoreNew' -and
    $task.Settings.ExecutionTimeLimit -eq 'PT0S' -and $task.Settings.RestartCount -eq 3 -and $task.Settings.RestartInterval -eq 'PT1M' -and -not $Credential) {
    Write-Output 'Завдання вже має вказану конфігурацію.'
    return
}
if (-not $PSCmdlet.ShouldProcess("$TaskName ($UserName)", 'Зареєструвати запуск HTTPS при старті Windows')) { return }
Assert-Project2Administrator
if (-not $Credential) { $Credential = Get-Credential -UserName $UserName -Message 'Введіть пароль облікового запису завдання Windows' }
if (-not $Credential -or (Get-AccountSid $Credential.UserName) -ne $sid) { throw 'Обліковий запис підтвердження має відповідати UserName.' }
Set-Project2PrivateDirectory $logDir @('server.log', 'server.log.1', 'server.log.2', 'server.log.3') $sid
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskPath '\' -TaskName $TaskName -Description $description -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -User $Credential.UserName -Password $Credential.GetNetworkCredential().Password -Force | Out-Null
Write-Output "Завдання зареєстровано. Журнал запуску: $log"
