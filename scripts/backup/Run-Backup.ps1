param(
    [Parameter(Mandatory=$true)][string]$BackupRepoRoot,
    [Parameter(Mandatory=$true)][string]$BackupPython,
    [Parameter(Mandatory=$true)][string]$BackupEnvFile
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $BackupRepoRoot
$env:PROJECT2_ENV_FILE = $BackupEnvFile
& $BackupPython -m app.services.backup run-once
$BackupExitCode = $LASTEXITCODE
if ($BackupExitCode -ne 0) {
    [Console]::Error.WriteLine('PROJECT2_BACKUP_FAILED: inspect the protected backup journal and Task Scheduler history.')
}
exit $BackupExitCode
