import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from processor.hook import HookOverlayRenderer

class TestHookOverlayRenderer(unittest.TestCase):
    def setUp(self):
        self.renderer = HookOverlayRenderer()
        self.test_dir = config.TEMP_MEDIA_DIR / "test_hook"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.source_video = self.test_dir / "source.mp4"
        
        # Create a dummy 5-second video if not exists
        if not self.source_video.exists():
            import subprocess
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=5:size=1080x1920:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                str(self.source_video)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_escape_text(self):
        escaped = HookOverlayRenderer._escape_text("hello: world, this is 'a' test %")
        self.assertEqual(escaped, "hello\\: world\\, this is \\'a\\' test \\%")

    def test_apply_all_empty(self):
        # When hook, watermark, and outro are empty, should return original path without changes
        res = self.renderer.apply(self.source_video, hook_text="", watermark_text="", outro_text="")
        self.assertEqual(res, self.source_video)

    def test_build_ffmpeg_command(self):
        cmd = self.renderer._build_ffmpeg_command(
            input_path=self.source_video,
            output_path=Path("dummy_out.mp4"),
            hook_text="INSANE PLAY",
            watermark_text="@testuser",
            outro_text="Subscribe!"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("drawtext=text='INSANE PLAY'", cmd_str)
        self.assertIn("drawtext=text='@testuser'", cmd_str)
        self.assertIn("drawtext=text='Subscribe!'", cmd_str)

    def test_apply_all_overlays(self):
        # Full render run on the dummy video
        res = self.renderer.apply(
            clip_path=self.source_video,
            hook_text="INSANE HOOK TEXT",
            watermark_text="@StreamClipper",
            outro_text="Follow for more!"
        )
        self.assertIsNotNone(res)
        self.assertEqual(res, self.source_video)
        self.assertTrue(self.source_video.exists())

    def tearDown(self):
        if self.source_video.exists():
            try:
                self.source_video.unlink()
            except Exception:
                pass
        try:
            self.test_dir.rmdir()
        except Exception:
            pass

if __name__ == "__main__":
    unittest.main()
