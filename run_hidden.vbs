Set WshShell = CreateObject("WScript.Shell")
strRootDir = "C:\Users\ismai\.gemini\antigravity\scratch\streamclipper"
WshShell.CurrentDirectory = strRootDir

' Kill existing processes first
WshShell.Run "powershell -Command ""Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue; Stop-Process -Id (Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue""", 0, True

' Start Backend hidden
WshShell.Run "python main.py", 0, False

' Start Frontend hidden
WshShell.CurrentDirectory = strRootDir & "\frontend"
WshShell.Run "cmd /c ""C:\Program Files\nodejs\npm.cmd"" run dev", 0, False
