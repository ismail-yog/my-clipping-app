import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from processor.thumbnail import ThumbnailGenerator

class TestThumbnailGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = ThumbnailGenerator()
        self.test_dir = config.TEMP_MEDIA_DIR / "test_thumbnail"
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

    def test_extract_frame(self):
        temp_png = self.test_dir / "frame.png"
        success = self.generator._extract_frame(self.source_video, temp_png)
        self.assertTrue(success)
        self.assertTrue(temp_png.exists())
        
        # Clean up
        temp_png.unlink()

    def test_add_text_overlay(self):
        temp_png = self.test_dir / "frame.png"
        output_jpg = self.test_dir / "thumbnail.jpg"
        
        # First extract a frame
        self.generator._extract_frame(self.source_video, temp_png)
        
        # Test drawing overlay
        result = self.generator._add_text_overlay(
            image_path=temp_png,
            text="INSANE OUTPLAY",
            streamer_name="shroud",
            output_path=output_jpg
        )
        self.assertIsNotNone(result)
        self.assertTrue(output_jpg.exists())
        self.assertEqual(result, output_jpg)
        
        # Clean up
        temp_png.unlink()
        output_jpg.unlink()

    def test_full_generate(self):
        result = self.generator.generate(
            clip_path=self.source_video,
            title_text="OH MY GOD",
            streamer_name="ninja"
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.exists())
        self.assertEqual(result.suffix, ".jpg")
        
        # Clean up
        result.unlink()

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
