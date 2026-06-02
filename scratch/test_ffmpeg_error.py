import sys
from pathlib import Path
import subprocess

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from processor.smart_crop import SmartCrop
from processor.audio_engine import AudioEngine

def test_ffmpeg():
    print("=========================================")
    print("🔬 Debugging FFmpeg Render Command")
    print("=========================================")
    
    # Locate active temp directory
    temp_dirs = list(config.TEMP_MEDIA_DIR.glob("vod_*"))
    if not temp_dirs:
        print("Error: No active temp directories found")
        return
        
    temp_dir = temp_dirs[0]
    source = temp_dir / "video.mp4"
    if not source.exists():
        print(f"Error: Source video not found at {source}")
        return
        
    output = config.CLIPS_DIR / "debug_test_output.mp4"
    if output.exists():
        output.unlink()
        
    # Generate simple test subtitle file
    sub_path = config.CLIPS_DIR / "debug_test.ass"
    sub_content = """[Script Info]
Title: Debug
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,90,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\c&H00FFFF&}HELLO{\\c&HFFFFFF&} WORLD
"""
    sub_path.write_text(sub_content, encoding="utf-8")
    
    # Run variables
    start = 10.0
    duration = 5.0
    layout_type = "basic"
    
    sc = SmartCrop()
    audio_engine = AudioEngine()

    filter_complex = sc.get_crop_filter(source, start, 1080, 1920, layout_type=layout_type, duration=duration)
    video_filter = "[0:v]" + filter_complex + "[v_out]"

    if sub_path and sub_path.exists():
        # Windows ASS filter needs specific escaping
        sub_escaped = str(sub_path.absolute()).replace("\\", "/").replace(":", "\\:")
        video_filter += f";[v_out]ass='{sub_escaped}'[v_captioned]"
        v_output_label = "[v_captioned]"
    else:
        v_output_label = "[v_out]"

    # Build audio filter graph and get extra input files (BGM, SFX)
    audio_filter, extra_inputs = audio_engine.build_audio_filter(
        duration=duration,
        has_sfx=True,
        sfx_name="vine_boom",
        sfx_offset_sec=duration * 0.7,
    )

    full_filter_complex = video_filter + ";" + audio_filter

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0, start)),
        "-i", str(source),
    ]

    cmd.extend(extra_inputs)

    cmd.extend([
        "-t", str(duration),
        "-filter_complex", full_filter_complex,
        "-map", v_output_label,
        "-map", "[a_out]",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-r", "30",
        "-movflags", "+faststart",
        str(output),
    ])
    
    print("\nRunning command:")
    print(" ".join(cmd))
    print("\nExecuting...")
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    
    print(f"\nReturn Code: {res.returncode}")
    print("\n--- STDOUT ---")
    print(res.stdout)
    print("\n--- STDERR ---")
    print(res.stderr)
    
    if output.exists():
        print(f"\nSuccess! Generated file size: {output.stat().st_size} bytes")
        # Clean up
        output.unlink()
    else:
        print("\nFailure! Output file was not created.")
        
    if sub_path.exists():
        sub_path.unlink()

if __name__ == "__main__":
    test_ffmpeg()
