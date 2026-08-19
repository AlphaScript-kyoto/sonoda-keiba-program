# Register the 3 Sonoda automation tasks for this machine.
# Run from an elevated or normal PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\register_server_tasks.ps1
#
# Recreates (overwrite) tasks matching the home-PC settings as of 2026-08-01.

[CmdletBinding()]
param(
    [string]$Root = "",
    [switch]$DisableExisting
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Root = $Root.TrimEnd("\")

$watchVbs = Join-Path $Root "scripts\start_watch_race_day.vbs"
$runVbs = Join-Path $Root "scripts\start_run_today.vbs"
$hbVbs = Join-Path $Root "scripts\start_check_watch_heartbeat.vbs"
$pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"

foreach ($p in @($watchVbs, $runVbs, $hbVbs)) {
    if (-not (Test-Path $p)) {
        throw "Missing launcher: $p"
    }
}
if (-not (Test-Path $pythonw)) {
    Write-Warning ".venv\Scripts\pythonw.exe not found. Create venv and pip install before relying on tasks."
}

function New-SonodaAction([string]$VbsPath) {
    return New-ScheduledTaskAction `
        -Execute "wscript.exe" `
        -Argument ("`"{0}`"" -f $VbsPath) `
        -WorkingDirectory $Root
}

function Register-OrReplaceTask {
    param(
        [string]$Name,
        $Action,
        $Trigger,
        $Settings
    )
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "Replaced existing task: $Name"
    }
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $Name `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $principal `
        -Force | Out-Null
    Write-Host "Registered: $Name"
}

# --- 1) 園田_当日監視 : daily 09:00, unlimited runtime ---
$watchSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries:$false `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$watchTrigger = New-ScheduledTaskTrigger -Daily -At 9:00am
Register-OrReplaceTask -Name "園田_当日監視" `
    -Action (New-SonodaAction $watchVbs) `
    -Trigger $watchTrigger `
    -Settings $watchSettings

# --- 2) 心拍チェック(20min) : daily 09:00, repeat every 15 min for 12 hours ---
$hbSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries:$false `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew
$hbTrigger = New-ScheduledTaskTrigger -Daily -At 9:00am
$hbTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At 9:00am -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Hours 12)).Repetition
Register-OrReplaceTask -Name "心拍チェック(20min)" `
    -Action (New-SonodaAction $hbVbs) `
    -Trigger $hbTrigger `
    -Settings $hbSettings

# --- 3) 園田_夜間取得 : daily 21:00, 2h limit ---
$nightSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries:$false `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew
$nightTrigger = New-ScheduledTaskTrigger -Daily -At 9:00pm
Register-OrReplaceTask -Name "園田_夜間取得" `
    -Action (New-SonodaAction $runVbs) `
    -Trigger $nightTrigger `
    -Settings $nightSettings

Write-Host ""
Write-Host "Root: $Root"
Get-ScheduledTask -TaskName "園田_当日監視","園田_夜間取得","心拍チェック(20min)" |
    Format-Table TaskName, State, @{N="Next";E={(Get-ScheduledTaskInfo $_).NextRunTime}} -AutoSize

Write-Host ""
Write-Host "IMPORTANT: Disable the same 3 tasks on the old PC to avoid duplicate notifications."
Write-Host "Smoke test: Start-ScheduledTask -TaskName '園田_当日監視'"