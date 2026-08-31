$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    $scriptDir = (Get-Location).Path
}

$WshShell = New-Object -ComObject WScript.Shell
$startupDir = [System.Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupDir 'StreamClipLauncher.lnk'

$targetVbs = Join-Path $scriptDir 'run_hidden.vbs'

$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $targetVbs
$Shortcut.WorkingDirectory = $scriptDir
$Shortcut.Description = "StreamClip AI Autonomous Daemon"
$Shortcut.Save()

Write-Host "[OK] Windows Startup Shortcut Registered Successfully"
Write-Host "     Shortcut Location: $shortcutPath"
Write-Host "     Target VBS:        $targetVbs"
Write-Host "     Working Directory: $scriptDir"
