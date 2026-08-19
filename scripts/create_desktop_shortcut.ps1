# Create Desktop shortcut for Sonoda Predict desktop app (no console)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Vbs = Join-Path $Root "scripts\start_predict_desktop.vbs"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "SonodaPredict.lnk"

if (-not (Test-Path $Vbs)) {
    throw "Launcher not found: $Vbs"
}

$Wsh = New-Object -ComObject WScript.Shell
$Sc = $Wsh.CreateShortcut($ShortcutPath)
$Sc.TargetPath = "wscript.exe"
$Sc.Arguments = "`"$Vbs`""
$Sc.WorkingDirectory = $Root
$Sc.WindowStyle = 7
$Sc.Description = "Sonoda race-day predict desktop (no console)"
$Sc.Save()
Write-Host ("Created: " + $ShortcutPath)