$WshShell = New-Object -ComObject WScript.Shell
$path = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\StreamClipLauncher.lnk'
$Shortcut = $WshShell.CreateShortcut($path)
$Shortcut.TargetPath = 'C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\run_hidden.vbs'
$Shortcut.Save()
Write-Host "Startup shortcut created at: $path"
