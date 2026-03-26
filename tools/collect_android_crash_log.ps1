$ErrorActionPreference = "Continue"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$adbPath = Join-Path $projectRoot "tools\platform-tools\adb.exe"
$logsDir = Join-Path $projectRoot "logs"
$adbServerPort = if ($env:ALIAS_ADB_SERVER_PORT) { $env:ALIAS_ADB_SERVER_PORT } else { "5037" }

if (-not (Test-Path $adbPath)) {
    Write-Host "ADB not found: $adbPath" -ForegroundColor Red
    Write-Host "Tell me and I will reinstall platform-tools automatically." -ForegroundColor Yellow
    exit 1
}

function Invoke-Adb {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Args,
        [switch] $IgnoreErrors
    )

    $allArgs = @("-P", $adbServerPort) + $Args
    $output = & $adbPath @allArgs 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0 -and -not $IgnoreErrors) {
        $joined = ($output | ForEach-Object { "$_" }) -join "`n"
        throw "ADB command failed (exit $exitCode): adb $($Args -join ' ')`n$joined"
    }

    return ($output | ForEach-Object { "$_" })
}

function Get-ConnectedDeviceSerial {
    param(
        [string[]] $RawList
    )

    $deviceLines = $RawList |
        Select-Object -Skip 1 |
        Where-Object { $_ -match "^\S+\s+device$" }

    if (-not $deviceLines) {
        return $null
    }

    return (($deviceLines | Select-Object -First 1) -split "\s+")[0]
}

function Ensure-Device {
    $devicesList = Invoke-Adb -Args @("devices")
    $serial = Get-ConnectedDeviceSerial -RawList $devicesList
    if ($serial) {
        return @{ Serial = $serial; List = $devicesList }
    }

    foreach ($endpoint in @("127.0.0.1:5555", "127.0.0.1:5556", "127.0.0.1:5565")) {
        Invoke-Adb -Args @("connect", $endpoint) -IgnoreErrors | Out-Null
    }

    Start-Sleep -Milliseconds 700
    $devicesList = Invoke-Adb -Args @("devices")
    $serial = Get-ConnectedDeviceSerial -RawList $devicesList
    return @{ Serial = $serial; List = $devicesList }
}

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

Write-Host "Checking ADB connection..." -ForegroundColor Cyan
Invoke-Adb -Args @("kill-server") -IgnoreErrors | Out-Null
Invoke-Adb -Args @("start-server") | Out-Null

$probe = Ensure-Device
$deviceSerial = $probe.Serial

if ([string]::IsNullOrWhiteSpace($deviceSerial)) {
    Write-Host ""
    Write-Host "No Android device found." -ForegroundColor Red
    Write-Host "If you use BlueStacks: Settings -> Advanced -> Enable Android Debug Bridge (ADB)." -ForegroundColor Yellow
    Write-Host "Then run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "Device detected: $deviceSerial" -ForegroundColor Green
Write-Host "Clearing old logs..." -ForegroundColor Green
Invoke-Adb -Args @("-s", $deviceSerial, "logcat", "-c") | Out-Null

Write-Host ""
Write-Host "Now do this:" -ForegroundColor Cyan
Write-Host "1) Launch Alias in BlueStacks" -ForegroundColor White
Write-Host "2) Wait until it crashes" -ForegroundColor White
Write-Host "3) Return here and press Enter" -ForegroundColor White
Read-Host "Press Enter after crash"

# Re-check device before collecting logs to avoid endless 'waiting for device'
$probe = Ensure-Device
$deviceSerial = $probe.Serial
if ([string]::IsNullOrWhiteSpace($deviceSerial)) {
    Write-Host "Device disconnected before log collection." -ForegroundColor Red
    exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$rawLogPath = Join-Path $logsDir ("alias_crash_raw_" + $timestamp + ".txt")
$filteredLogPath = Join-Path $logsDir ("alias_crash_" + $timestamp + ".txt")

Write-Host "Collecting logcat..." -ForegroundColor Green
$rawLog = Invoke-Adb -Args @("-s", $deviceSerial, "logcat", "-d")
$rawLog | Out-File -FilePath $rawLogPath -Encoding utf8

$regex = "(?i)(FATAL EXCEPTION|AndroidRuntime|Traceback|python|kivy|alias|ModuleNotFoundError|ImportError|No module named)"
$filteredLines = $rawLog | Where-Object { $_ -match $regex }

if ($filteredLines.Count -gt 0) {
    $filteredLines | Out-File -FilePath $filteredLogPath -Encoding utf8
} else {
    "No filtered lines found. Use raw log: $rawLogPath" | Out-File -FilePath $filteredLogPath -Encoding utf8
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "RAW log:      $rawLogPath" -ForegroundColor White
Write-Host "Filtered log: $filteredLogPath" -ForegroundColor White
Write-Host ""
Write-Host "Send me the filtered log file." -ForegroundColor Cyan
