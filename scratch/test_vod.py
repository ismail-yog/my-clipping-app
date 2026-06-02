import os
import sys
import shutil
import uuid
import unittest
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from database import Database
from processor.vod import VODProcessor

class TestVODProcessing(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.processor = VODProcessor(self.db)
        
        # Clean up remnants from previous runs to avoid UNIQUE constraint violations
        self.db.delete_clip("vod_testvod_0")
        for f in config.CLIPS_DIR.glob("vod_testvod_*"):
            try:
                f.unlink()
            except Exception:
                pass
        
        # Paths
        self.source_clip = config.CLIPS_DIR / "hasanabi_1779308442.mp4"
        self.assertTrue(self.source_clip.exists(), f"Source clip not found at {self.source_clip}")
        
        # Prepare mock music and SFX
        win_media_dir = Path("C:/Windows/Media")
        self.music_dest = config.BASE_DIR / "assets" / "music" / "test_bgm.wav"
        self.sfx_dest = config.BASE_DIR / "assets" / "sfx" / "vine_boom.wav"
        
        self.music_dest.parent.mkdir(parents=True, exist_ok=True)
        self.sfx_dest.parent.mkdir(parents=True, exist_ok=True)
        
        if win_media_dir.exists():
            chimes_src = win_media_dir / "chimes.wav"
            if chimes_src.exists() and not self.music_dest.exists():
                shutil.copy(chimes_src, self.music_dest)
            
            ding_src = win_media_dir / "ding.wav"
            if ding_src.exists() and not self.sfx_dest.exists():
                shutil.copy(ding_src, self.sfx_dest)

    def test_vod_processor_pipeline(self):
        print("\n" + "=" * 60)
        print("🤖 Running VOD Processor Upgrade Test Suite")
        print("=" * 60)
        
        # We patch processor.run_subprocess to skip downloading since we pre-copy the video
        original_run = self.processor.run_subprocess
        
        # We pre-determine the VOD ID
        vid = "testvod"
        temp_dir = config.TEMP_MEDIA_DIR / f"vod_{vid}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        video_path = temp_dir / "video.mp4"
        # Copy source clip to video_path
        shutil.copy(self.source_clip, video_path)
        print(f"Pre-copied source video to: {video_path}")
        
        import subprocess
        
        def mock_run_subprocess(cmd, timeout=None, capture_output=True, text=True):
            if cmd[0] == "yt-dlp":
                print("Mocking yt-dlp download: SUCCESS")
                return subprocess.CompletedProcess(cmd, 0, "mock stdout", "mock stderr")
            return original_run(cmd, timeout=timeout, capture_output=capture_output, text=text)
            
        self.processor.run_subprocess = mock_run_subprocess
        
        # We temporarily patch process_url to use our fixed VOD ID "testvod"
        original_process_url = self.processor.process_url
        
        def patched_process_url(url, job_id="", layout_type="gamer"):
            import uuid
            class MockUUID(str):
                @property
                def hex(self):
                    return "testvod"
            uuid.uuid4 = lambda: MockUUID("testvod")
            try:
                return original_process_url(url, job_id, layout_type)
            finally:
                pass
                
        # Run processing pipeline on a dummy URL
        success = patched_process_url("https://www.youtube.com/watch?v=dummy", job_id="testjob", layout_type="gamer")
        
        self.assertTrue(success, "VOD processing pipeline failed")
        print("\n🎉 VOD processing pipeline completed successfully!")
        
        # Verify that clips were generated and stored in clips/
        generated_clips = list(config.CLIPS_DIR.glob("vod_testvod_*.mp4"))
        self.assertGreater(len(generated_clips), 0, "No clips generated")
        print(f"Verified generated clips in directory:")
        for gc in generated_clips:
            print(f"  - {gc.name} (size: {gc.stat().st_size} bytes)")
            
            # Check metadata in DB
            clip_id = gc.stem
            db_clip = self.db.get_clip(clip_id)
            self.assertIsNotNone(db_clip, f"Clip record not found in DB for {clip_id}")
            
            # Check subtitle file
            ass_file = gc.with_suffix(".ass")
            self.assertTrue(ass_file.exists(), f"Subtitle file not found for {gc.name}")
            print(f"    - Subtitle path: {ass_file.name}")
            print(f"    - DB Record title: {db_clip.get('title')}")
            
            # Read first few lines of subtitle file to check Arial Black styling
            sub_content = ass_file.read_text(encoding="utf-8")
            self.assertIn("Arial Black", sub_content, "Subtitle style does not use Arial Black font")
            print("    - Arial Black font styling: VERIFIED")
            
        print("=" * 60)
        
    def tearDown(self):
        self.db.close()

if __name__ == "__main__":
    unittest.main()
