#requires -Version 5.1
[CmdletBinding()]
param([string]$ServerName='foxlys.local', [ValidateRange(1,65535)][int]$Port=8443, [ValidateRange(1,60)][int]$TimeoutSeconds=10)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Project2Lan.psm1')
Assert-Project2ServerName $ServerName
$devices = @(Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.HasPrivateKey -and (Test-Project2DeviceCertificate $_ -Current)
} | Sort-Object NotBefore -Descending)
if (-not $devices.Count) { throw 'На цьому ПК немає сертифіката пристрою Project 2 → Install-Project2DeviceCert.ps1.' }
$certs = [Security.Cryptography.X509Certificates.X509CertificateCollection]::new()
[void]$certs.Add($devices[0])
$protocols = [Security.Authentication.SslProtocols]::Tls12
if ('Tls13' -in [Enum]::GetNames([Security.Authentication.SslProtocols])) {
    $protocols = $protocols -bor [Security.Authentication.SslProtocols]::Tls13
}
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
        $tls.AuthenticateAsClient($ServerName, $certs, $protocols, $false)
        if (-not $tls.IsMutuallyAuthenticated) { throw 'Сервер не підтвердив взаємну TLS-автентифікацію.' }
        Write-Output "TLS: імʼя сертифіката та ланцюжок довіри перевірено ($($tls.SslProtocol))."
        $query = [Text.Encoding]::ASCII.GetBytes("GET /auth/login HTTP/1.1`r`nHost: ${ServerName}:$Port`r`nConnection: close`r`n`r`n")
        $tls.Write($query, 0, $query.Length)
        $reader = [IO.StreamReader]::new($tls, [Text.Encoding]::ASCII)
        try {
            $statusLine = $reader.ReadLine()
            $hsts = $false
            while ($line = $reader.ReadLine()) {
                if ($line -match '^Strict-Transport-Security:\s*max-age=31536000\s*$') { $hsts = $true }
            }
        } finally { $reader.Dispose() }
        if (-not $hsts) { throw 'Сервер не повернув очікуваний Strict-Transport-Security.' }
        if ($statusLine -notmatch '^HTTP/1\.[01] 200( |$)') { throw "Форма входу не повернула HTTP 200 ($statusLine)." }
        Write-Output "HTTP 200, mTLS і HSTS перевірено. Сторінка входу доступна за https://${ServerName}:$Port/auth/login"
    } catch {
        throw "Перевірте довіру до серверного CA, строк сертифіката пристрою та його відкликання у CRL. $($_.Exception.Message)"
    } finally { $tls.Dispose() }
} finally { $socket.Dispose() }
