import os
import shutil
import time
from pathlib import Path
from processor.clipper import Clipper
from processor.hook import HookOverlayRenderer
from detector.sentiment import TranscriptSegment, TranscriptWord
import config

def run_test():
    print("=" * 60)
    print("🚀 Running Video Editing Pipeline Upgrade Test")
    print("=" * 60)

    # 1. Copy sample media files from Windows Media folder for BGM and SFX
    win_media_dir = Path("C:/Windows/Media")
    music_dest = config.BASE_DIR / "assets" / "music" / "test_bgm.wav"
    sfx_dest = config.BASE_DIR / "assets" / "sfx" / "vine_boom.wav"

    # Make sure folders are initialized
    music_dest.parent.mkdir(parents=True, exist_ok=True)
    sfx_dest.parent.mkdir(parents=True, exist_ok=True)

    # Try copying chimes.wav for BGM
    chimes_src = win_media_dir / "chimes.wav"
    if chimes_src.exists():
        shutil.copy(chimes_src, music_dest)
        print(f"Copied test BGM: {music_dest.name}")
    else:
        # Fallback empty or mock
        print("Warning: Windows chimes.wav not found. Running test without BGM.")

    # Try copying ding.wav for SFX
    ding_src = win_media_dir / "ding.wav"
    if ding_src.exists():
        shutil.copy(ding_src, sfx_dest)
        print(f"Copied test SFX: {sfx_dest.name}")
    else:
        print("Warning: Windows ding.wav not found. Running test without SFX.")

    # 2. Setup input clip path
    input_clip = config.CLIPS_DIR / "hasanabi_1779308442.mp4"
    if not input_clip.exists():
        print(f"Error: Test clip not found at {input_clip}")
        return

    # 3. Create mock transcript segments with word timings
    # We will include words that trigger emojis: "insane", "dead", "fire", "win"
    words = [
        TranscriptWord(word="Guys", start=0.5, end=0.8, probability=0.9),
        TranscriptWord(word="this", start=0.8, end=1.0, probability=0.9),
        TranscriptWord(word="is", start=1.0, end=1.2, probability=0.9),
        TranscriptWord(word="insane", start=1.2, end=1.8, probability=0.95),  # 🤯
        TranscriptWord(word="we", start=1.8, end=2.0, probability=0.9),
        TranscriptWord(word="got", start=2.0, end=2.2, probability=0.9),
        TranscriptWord(word="the", start=2.2, end=2.4, probability=0.9),
        TranscriptWord(word="win", start=2.4, end=3.0, probability=0.95),     # 🏆
        TranscriptWord(word="he", start=3.0, end=3.2, probability=0.9),
        TranscriptWord(word="is", start=3.2, end=3.4, probability=0.9),
        TranscriptWord(word="dead", start=3.4, end=3.8, probability=0.95),    # 💀
        TranscriptWord(word="this", start=3.8, end=4.0, probability=0.9),
        TranscriptWord(word="is", start=4.0, end=4.2, probability=0.9),
        TranscriptWord(word="pure", start=4.2, end=4.5, probability=0.9),
        TranscriptWord(word="fire", start=4.5, end=5.0, probability=0.95),    # 🔥
    ]

    segments = [
        TranscriptSegment(start=0.5, end=5.0, text="Guys this is insane we got the win he is dead this is pure fire", words=words)
    ]

    # 4. Instantiate components
    clipper = Clipper()
    hook_renderer = HookOverlayRenderer()

    # 5. Create Clip with layout_type="gamer" (split screen & dynamic face tracking)
    print("\n🎬 Step 1: Processing clip with dynamic crop and word-chunked captions...")
    test_clip_id = f"test_render_{int(time.time())}"
    
    metadata = clipper.create_clip(
        source_video=input_clip,
        streamer=None,
        start_offset=0.0,
        duration=10,  # 10 second test clip
        moment_score=0.95,
        transcript_segments=segments,
        emotion="joy",
        custom_clip_id=test_clip_id,
        layout_type="gamer",
    )

    if not metadata:
        print("❌ Clip creation failed!")
        return

    clip_output_path = Path(metadata.clip_path)
    print(f"✅ Clip created: {clip_output_path.absolute()}")

    # 6. Apply Hook Overlay, Watermark, and Outro Fades
    print("\n✨ Step 2: Overlaying Hook title, corner watermark, and outro cards...")
    final_output = hook_renderer.apply(
        clip_path=clip_output_path,
        hook_text="INSANE WIN 🏆",
        watermark_text="@HasanAbi",
    )

    if not final_output or not final_output.exists():
        print("❌ Hook overlay failed!")
        return

    print(f"✅ Final processed video ready at: {final_output.absolute()}")
    print("=" * 60)
    print("🎉 Upgrades verified successfully!")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
