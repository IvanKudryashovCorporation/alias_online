param(
    [string]$AdbPath = "C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    [string]$Device = "127.0.0.1:5555",
    [string]$Package = "com.aliasonline.aliasonline",
    [string]$ApkPath = "",
    [string]$LogsDir = "",
    [switch]$ClearData
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $AdbPath)) {
    throw "ADB not found: $AdbPath"
}

if ([string]::IsNullOrWhiteSpace($LogsDir)) {
    $projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    $LogsDir = Join-Path $projectRoot "logs"
}
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logcatPath = Join-Path $LogsDir "apk_smoke_$timestamp.logcat.txt"
$shotFastPng = Join-Path $LogsDir "apk_smoke_${timestamp}_t8.png"
$shotFastJpg = Join-Path $LogsDir "apk_smoke_${timestamp}_t8.jpg"
$shotSlowPng = Join-Path $LogsDir "apk_smoke_${timestamp}_t30.png"
$shotSlowJpg = Join-Path $LogsDir "apk_smoke_${timestamp}_t30.jpg"
$summaryPath = Join-Path $LogsDir "apk_smoke_${timestamp}_summary.txt"

function Run-Adb {
    param(
        [string[]]$CommandArgs,
        [switch]$AllowFailure
    )
    $safeArgs = @($CommandArgs | Where-Object { $_ -ne $null -and "$_".Length -gt 0 })
    if ($safeArgs.Count -eq 0) {
        throw "ADB command args are empty."
    }

    $stdOutPath = [System.IO.Path]::GetTempFileName()
    $stdErrPath = [System.IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process -FilePath $AdbPath -ArgumentList $safeArgs -NoNewWindow -PassThru -Wait -RedirectStandardOutput $stdOutPath -RedirectStandardError $stdErrPath
        $stdOut = if (Test-Path $stdOutPath) { Get-Content -Path $stdOutPath -Raw -ErrorAction SilentlyContinue } else { "" }
        $stdErr = if (Test-Path $stdErrPath) { Get-Content -Path $stdErrPath -Raw -ErrorAction SilentlyContinue } else { "" }
        $exitCode = $proc.ExitCode
        $output = "$stdOut$stdErr"
    } finally {
        if (Test-Path $stdOutPath) { Remove-Item -LiteralPath $stdOutPath -Force -ErrorAction SilentlyContinue }
        if (Test-Path $stdErrPath) { Remove-Item -LiteralPath $stdErrPath -Force -ErrorAction SilentlyContinue }
    }
    if (-not $AllowFailure -and $exitCode -ne 0) {
        $joinedArgs = ($safeArgs -join " ")
        throw "ADB command failed (exit=$exitCode): $joinedArgs`n$output"
    }
    return $output
}

function Capture-Shot {
    param(
        [string]$RemoteName,
        [string]$LocalPng,
        [string]$LocalJpg
    )
    Run-Adb -CommandArgs @("-s", $Device, "shell", "screencap", "-p", "/sdcard/$RemoteName")
    Run-Adb -CommandArgs @("-s", $Device, "pull", "/sdcard/$RemoteName", $LocalPng) | Out-Null
    python -c "from PIL import Image; Image.open(r'$LocalPng').convert('RGB').save(r'$LocalJpg', quality=92)"
}

Run-Adb -CommandArgs @("devices") | Out-Null

if (-not [string]::IsNullOrWhiteSpace($ApkPath)) {
    if (-not (Test-Path $ApkPath)) {
        throw "APK not found: $ApkPath"
    }
    try {
            Run-Adb -CommandArgs @("-s", $Device, "install", "-r", "-g", $ApkPath) | Out-Null
    } catch {
        if ($_.Exception.Message -match "INSTALL_FAILED_UPDATE_INCOMPATIBLE") {
            Run-Adb -CommandArgs @("-s", $Device, "uninstall", $Package) | Out-Null
            Run-Adb -CommandArgs @("-s", $Device, "install", "-g", $ApkPath) | Out-Null
        } else {
            throw
        }
    }
}

if ($ClearData.IsPresent) {
    Run-Adb -CommandArgs @("-s", $Device, "shell", "pm", "clear", $Package) -AllowFailure | Out-Null
}

Run-Adb -CommandArgs @("-s", $Device, "logcat", "-c")
Run-Adb -CommandArgs @("-s", $Device, "shell", "monkey", "-p", $Package, "-c", "android.intent.category.LAUNCHER", "1") | Out-Null

Start-Sleep -Seconds 8
$pidT8 = (Run-Adb -CommandArgs @("-s", $Device, "shell", "pidof", $Package) -AllowFailure)
Capture-Shot -RemoteName "apk_smoke_t8.png" -LocalPng $shotFastPng -LocalJpg $shotFastJpg

Start-Sleep -Seconds 22
$pidT30 = (Run-Adb -CommandArgs @("-s", $Device, "shell", "pidof", $Package) -AllowFailure)
Capture-Shot -RemoteName "apk_smoke_t30.png" -LocalPng $shotSlowPng -LocalJpg $shotSlowJpg

Run-Adb -CommandArgs @("-s", $Device, "logcat", "-d") | Set-Content -Path $logcatPath -Encoding UTF8

$blackRatioRaw = python -c "from PIL import Image; import re; im=Image.open(r'$shotFastJpg').convert('RGB'); px=im.getdata(); total=len(px); black=sum(1 for r,g,b in px if r<8 and g<8 and b<8); print(round(black/total,4))"
$ratioText = ($blackRatioRaw -join "").Trim()
$ratioMatch = [regex]::Match($ratioText, "\d+(\.\d+)?")
$blackRatio = if ($ratioMatch.Success) { [double]$ratioMatch.Value } else { -1.0 }

$critical = Select-String -Path $logcatPath -Pattern "Traceback|FATAL EXCEPTION|\[CRITICAL\]|ModuleNotFoundError|ImportError|Unhandled exception" -CaseSensitive:$false

$summary = @()
$summary += "APK smoke timestamp: $timestamp"
$summary += "Package: $Package"
$summary += "Clear data before launch: $($ClearData.IsPresent)"
$summary += "PID @t8: $pidT8"
$summary += "PID @t30: $pidT30"
$summary += "Screenshot t8: $shotFastJpg"
$summary += "Screenshot t30: $shotSlowJpg"
$summary += "Black pixel ratio @t8: $blackRatio"
$summary += "Logcat: $logcatPath"
$summary += "Critical log matches: $($critical.Count)"

if ($critical.Count -gt 0) {
    $summary += ""
    $summary += "Critical log excerpts:"
    $summary += ($critical | Select-Object -First 25 | ForEach-Object { $_.Line })
}

$summary | Set-Content -Path $summaryPath -Encoding UTF8
Write-Output "Smoke summary: $summaryPath"
Write-Output ($summary -join [Environment]::NewLine)
