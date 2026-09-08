Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

' Dynamically resolve script directory so no paths are hardcoded
strRootDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strRootDir

' Kill existing processes holding ports 8000 (Backend) and 3000 (Frontend)
WshShell.Run "powershell -WindowStyle Hidden -Command ""Get-NetTCPConnection -LocalPort 8000,3000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }""", 0, True

' Start Backend hidden using PATH resolution
WshShell.CurrentDirectory = strRootDir
WshShell.Run "cmd /c python main.py", 0, False

' Start Frontend hidden using PATH resolution
WshShell.CurrentDirectory = strRootDir & "\frontend"
WshShell.Run "cmd /c npm run dev", 0, False
