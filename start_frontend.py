import subprocess

cwd = r"C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\frontend"
cmd = r'"C:\Program Files\nodejs\npm.cmd" run dev'

# Start the frontend detached in a new, independent console window
subprocess.Popen(cmd, cwd=cwd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
print("Frontend server started successfully!")
