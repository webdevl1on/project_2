#requires -Version 5.1
[CmdletBinding()]
param([string]$ServerName='foxlys.local', [ValidateRange(1,65535)][int]$Port=8443, [ValidateRange(1,60)][int]$TimeoutSeconds=10)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
Assert-Project2ServerName $ServerName
try { $addresses = [Net.Dns]::GetHostAddresses($ServerName) }
catch { throw "Не вдалося знайти $ServerName. Перевірте mDNS або позначений запис hosts." }
if (-not $addresses.Count) { throw "Системний резолвер не повернув адрес для $ServerName." }
Write-Output "Імʼя $ServerName знайдено: $($addresses -join ', ')"
$socket = $null
foreach ($address in $addresses) {
    $candidate = [Net.Sockets.TcpClient]::new($address.AddressFamily)
    try {
        if ($candidate.ConnectAsync($address, $Port).Wait($TimeoutSeconds * 1000)) { $socket = $candidate; break }
    } catch [AggregateException] { Write-Verbose "Не вдалося підключитися до $address." }
    if ($null -eq $socket) { $candidate.Dispose() }
}
if ($null -eq $socket) { throw "TCP-порт $Port недоступний. Перевірте завдання сервера, порт і профіль Firewall." }
try {
    Write-Output "TCP-зʼєднання з портом $Port встановлено."
    $socket.ReceiveTimeout = $socket.SendTimeout = $TimeoutSeconds * 1000
    $tls = [Net.Security.SslStream]::new($socket.GetStream(), $false)
    try {
        # Default Windows chain and DNS-name validation; never install a validation callback.
        $tls.AuthenticateAsClient($ServerName)
        Write-Output "TLS: імʼя сертифіката та ланцюжок довіри перевірено ($($tls.SslProtocol))."
        $query = [Text.Encoding]::ASCII.GetBytes("GET /auth/login HTTP/1.1`r`nHost: ${ServerName}:$Port`r`nConnection: close`r`n`r`n")
        $tls.Write($query, 0, $query.Length)
        $reader = [IO.StreamReader]::new($tls, [Text.Encoding]::ASCII)
        try { $statusLine = $reader.ReadLine() } finally { $reader.Dispose() }
        if ($statusLine -notmatch '^HTTP/1\.[01] 200( |$)') { throw "Форма входу не повернула HTTP 200 ($statusLine)." }
        Write-Output "HTTP 200. Сторінка входу доступна за https://${ServerName}:$Port/auth/login"
    } finally { $tls.Dispose() }
} finally { $socket.Dispose() }
