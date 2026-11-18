param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][string]$SignalDirectory,
    [int]$DurationSeconds=240,
    [ValidateSet('all','nics')][string]$Components='nics'
)
$ErrorActionPreference='Stop'
$outputRoot=[IO.Path]::GetFullPath($OutputDirectory)
$signalRoot=[IO.Path]::GetFullPath($SignalDirectory)
New-Item -ItemType Directory -Force -Path $outputRoot,$signalRoot | Out-Null
$logPath=Join-Path $outputRoot 'capture-console.txt'
$started=$false
$addedFilters=@()
try {
    $current=(& pktmon status 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw $current }
    if ($current -match '\brunning\b' -and $current -notmatch '\bnot running\b') { throw 'Another PktMon session is running; it has not been stopped.' }
    foreach ($entry in @(@('MCT431_Inspection',9000),@('MCT431_Operator',8000))) {
        $message=(& pktmon filter add $entry[0] -t TCP -p $entry[1] 2>&1 | Out-String)
        Add-Content -LiteralPath $logPath -Value $message
        if ($LASTEXITCODE -ne 0) { throw $message }
        $addedFilters+=$entry[0]
    }
    $etl=Join-Path $outputRoot 'milestone1.etl'
    $pcap=Join-Path $outputRoot 'milestone1.pcapng'
    $message=(& pktmon start --capture --comp $Components --pkt-size 0 --file-size 64 --file-name $etl 2>&1 | Out-String)
    Add-Content -LiteralPath $logPath -Value $message
    if ($LASTEXITCODE -ne 0) { throw $message }
    $started=$true
    @{started=(Get-Date).ToString('o');pcap=$pcap} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $signalRoot 'capture-ready.json')
    $deadline=(Get-Date).AddSeconds($DurationSeconds)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath (Join-Path $signalRoot 'stop-capture.flag'))) { Start-Sleep -Milliseconds 250 }
    $message=(& pktmon stop 2>&1 | Out-String);$started=$false
    Add-Content -LiteralPath $logPath -Value $message
    if ($LASTEXITCODE -ne 0) { throw $message }
    $message=(& pktmon etl2pcap $etl --out $pcap 2>&1 | Out-String)
    Add-Content -LiteralPath $logPath -Value $message
    if ($LASTEXITCODE -ne 0) { throw $message }
    @{pcap=$pcap;bytes=(Get-Item -LiteralPath $pcap).Length} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $signalRoot 'capture-complete.json')
} catch {
    @{error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $signalRoot 'capture-error.json')
} finally {
    if ($started) { & pktmon stop | Out-Null }
    foreach ($filterName in $addedFilters) { & pktmon filter remove $filterName | Out-Null }
}
