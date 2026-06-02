import sys
import logging
logging.basicConfig(level=logging.INFO)

print("Attempting to import faster-whisper...")
try:
    from faster_whisper import WhisperModel
    print("Import successful!")
    print("Initializing WhisperModel('base', device='cpu', compute_type='int8')...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    print("CPU Model loaded successfully!")
    
    print("Initializing WhisperModel('base', device='auto')...")
    model_auto = WhisperModel("base", device="auto")
    print("Auto Model loaded successfully!")
except Exception as e:
    print(f"Error occurred: {e}", file=sys.stderr)
