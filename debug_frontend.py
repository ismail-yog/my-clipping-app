import subprocess
import os

cwd = r"C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\frontend"
cmd = r'"C:\Program Files\nodejs\npm.cmd" run dev'

with open(r"C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\frontend\debug_output.log", "w") as f:
    try:
        p = subprocess.Popen(cmd, cwd=cwd, shell=True, stdout=f, stderr=f)
        f.write(f"Started PID: {p.pid}\n")
        p.wait()
        f.write(f"\nExited with code {p.returncode}\n")
    except Exception as e:
        f.write(f"\nException: {str(e)}\n")
