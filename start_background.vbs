Set WshShell = CreateObject("WScript.Shell")

' Start Backend (StreamClipper)
' Running with 0 to keep the window hidden
WshShell.Run "cmd /c ""cd /d C:\Users\ismai\.gemini\antigravity\scratch\streamclipper && python main.py""", 0, False

' Start Frontend (Next.js)
WshShell.Run "cmd /c ""cd /d C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\frontend && cmd /c npm run dev""", 0, False
