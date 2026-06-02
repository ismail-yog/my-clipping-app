import threading
import time
from faster_whisper import WhisperModel

def worker():
    print("Thread starting model load...")
    try:
        model = WhisperModel("base", device="cuda")
        print("Thread model load success!")
    except Exception as e:
        print("Thread model load failed:", e)

t = threading.Thread(target=worker)
t.start()
t.join()
print("Done!")
