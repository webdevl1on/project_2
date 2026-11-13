# Run explicitly as a Windows administrator after reviewing paths, credentials and config.
param(
    [Parameter(Mandatory=$true)][string]$BackupRepoRoot,
    [Parameter(Mandatory=$true)][string]$BackupPython,
    [Parameter(Mandatory=$true)][string]$BackupEnvFile,
    [Parameter(Mandatory=$true)][System.Management.Automation.PSCredential]$BackupCredential,
    [string]$BackupTaskName = 'Project2-Backup',
    [ValidateSet('Limited','Highest')][string]$BackupRunLevel = 'Limited'
)
$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName $BackupTaskName -ErrorAction SilentlyContinue) { throw 'Task already exists; inspect it rather than replacing it.' }
foreach ($BackupPath in @($BackupRepoRoot,$BackupPython,$BackupEnvFile)) {
    if (-not (Test-Path -LiteralPath $BackupPath)) { throw 'A configured backup path does not exist.' }
    if ($BackupPath.Contains('"')) { throw 'Unsupported quote in configured path.' }
}
$BackupScript = Join-Path $BackupRepoRoot 'scripts\backup\Run-Backup.ps1'
$BackupArguments = '-NoProfile -NonInteractive -File "{0}" -BackupRepoRoot "{1}" -BackupPython "{2}" -BackupEnvFile "{3}"' -f $BackupScript,$BackupRepoRoot,$BackupPython,$BackupEnvFile
$BackupAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $BackupArguments -WorkingDirectory $BackupRepoRoot
$BackupTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$BackupSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $BackupTaskName -Action $BackupAction -Trigger $BackupTrigger -Settings $BackupSettings -RunLevel $BackupRunLevel -User $BackupCredential.UserName -Password $BackupCredential.GetNetworkCredential().Password | Out-Null
Write-Output 'Backup worker task registered. Verify the first run and failure notifications.'
