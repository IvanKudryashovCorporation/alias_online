$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$adbPath = Join-Path $projectRoot "tools\platform-tools\adb.exe"
$logsDir = Join-Path $projectRoot "logs"
$adbServerPort = "5038"

if (-not (Test-Path $adbPath)) {
    Write-Host "ADB not found: $adbPath" -ForegroundColor Red
    Write-Host "Tell me and I will reinstall platform-tools automatically." -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

Write-Host "Checking ADB connection..." -ForegroundColor Cyan
try {
    & $adbPath -P $adbServerPort start-server | Out-Null
    $devicesList = & $adbPath -P $adbServerPort devices 2>&1
    $devicesOutput = $devicesList -join "`n"
} catch {
    Write-Host "ADB failed to start or connect." -ForegroundColor Red
    Write-Host "Close Android Studio/emulators and run this script again." -ForegroundColor Yellow
    Write-Host "Details: $($_.Exception.Message)" -ForegroundColor DarkYellow
    exit 1
}

if ($devicesOutput -match "unauthorized") {
    Write-Host ""
    Write-Host "Device is unauthorized." -ForegroundColor Yellow
    Write-Host "1) Unlock the phone" -ForegroundColor Yellow
    Write-Host "2) Tap 'Allow USB debugging'" -ForegroundColor Yellow
    Write-Host "3) Run this script again" -ForegroundColor Yellow
    exit 1
}

function Get-ConnectedDeviceSerial($rawList) {
    return (
        $rawList |
        Select-Object -Skip 1 |
        Where-Object { $_ -match "^\S+\s+device$" } |
        ForEach-Object { ($_ -split "\s+")[0] } |
        Select-Object -First 1
    )
}

$deviceSerial = Get-ConnectedDeviceSerial $devicesList

if ([string]::IsNullOrWhiteSpace($deviceSerial)) {
    foreach ($endpoint in @("127.0.0.1:5555", "127.0.0.1:5556", "127.0.0.1:5565")) {
        try {
            & $adbPath -P $adbServerPort connect $endpoint | Out-Null
        } catch {
        }
    }

    Start-Sleep -Seconds 1
    $devicesList = & $adbPath -P $adbServerPort devices 2>&1
    $deviceSerial = Get-ConnectedDeviceSerial $devicesList
}

if ([string]::IsNullOrWhiteSpace($deviceSerial)) {
    Write-Host ""
    Write-Host "No Android device found." -ForegroundColor Red
    Write-Host "If you use BlueStacks, open it first and enable ADB in BlueStacks settings." -ForegroundColor Yellow
    exit 1
}

Write-Host "Device detected. Clearing old logs..." -ForegroundColor Green
& $adbPath -P $adbServerPort -s $deviceSerial logcat -c

Write-Host ""
Write-Host "Now do this:" -ForegroundColor Cyan
Write-Host "1) Launch Alias app on phone" -ForegroundColor White
Write-Host "2) Wait until it crashes" -ForegroundColor White
Write-Host "3) Come back and press Enter" -ForegroundColor White
Read-Host "Press Enter after crash"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$rawLogPath = Join-Path $logsDir ("alias_crash_raw_" + $timestamp + ".txt")
$filteredLogPath = Join-Path $logsDir ("alias_crash_" + $timestamp + ".txt")

Write-Host "Collecting logcat..." -ForegroundColor Green
& $adbPath -P $adbServerPort -s $deviceSerial logcat -d 2>&1 | Out-File -FilePath $rawLogPath -Encoding utf8

$regex = "(?i)(FATAL EXCEPTION|AndroidRuntime|Traceback|python|kivy|alias)"
$filteredLines = Get-Content $rawLogPath | Where-Object { $_ -match $regex }

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
