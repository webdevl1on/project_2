#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess)]
param([string]$TaskName='Project2-LAN')
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
if ($TaskName -match '[*?\[\]\\/]') { throw 'Вкажіть точне імʼя завдання.' }
$task = Get-ScheduledTask -TaskPath '\' -TaskName $TaskName
if ($task.Description -ne 'Project 2 LAN: HTTPS (app.serve)' -or -not $task.Settings.Enabled) {
    throw 'Потрібне активне завдання HTTPS, створене Register-Project2Task.ps1.'
}
if (-not $PSCmdlet.ShouldProcess($TaskName, 'Перезапустити HTTPS-сервер і завантажити актуальний CRL')) { return }
Assert-Project2Administrator
if ($task.State -in @('Running','Queued')) {
    Stop-ScheduledTask -InputObject $task
    $limit = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 300
        $state = (Get-ScheduledTask -TaskPath '\' -TaskName $TaskName).State
    } while ($state -in @('Running','Queued') -and (Get-Date) -lt $limit)
    if ($state -in @('Running','Queued')) { throw 'Попередній процес не зупинився за 30 секунд.' }
}
Start-ScheduledTask -InputObject $task
$limit = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 400
    $state = (Get-ScheduledTask -TaskPath '\' -TaskName $TaskName).State
} while ($state -ne 'Running' -and (Get-Date) -lt $limit)
Start-Sleep -Seconds 2
if ((Get-ScheduledTask -TaskPath '\' -TaskName $TaskName).State -ne 'Running') {
    $code = (Get-ScheduledTaskInfo -TaskPath '\' -TaskName $TaskName).LastTaskResult
    throw "Завдання не працює. Код $code. Перевірте журнал запуску та строк CRL."
}
Write-Output 'Завдання працює. Виконайте Test-Project2Lan.ps1 від імені користувача браузера.'
