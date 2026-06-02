import subprocess
import sys
import time

cwd = r"C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\frontend"
cmd = r'"C:\Program Files\nodejs\npm.cmd" run dev'

# Open a log file
log_path = r"C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\frontend\frontend_detached.log"
log_file = open(log_path, "w")

# Launch the process in background
p = subprocess.Popen(
    cmd,
    cwd=cwd,
    shell=True,
    stdout=log_file,
    stderr=log_file,
    stdin=subprocess.DEVNULL
)

print(f"Started Next.js frontend in the background with PID: {p.pid}")
# Give it a brief moment to start
time.sleep(1)
sys.exit(0)
