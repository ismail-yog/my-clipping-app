import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from processor.clipper import ClipMetadata, Clipper
from detector.sentiment import TranscriptSegment, TranscriptWord

class TestClipper(unittest.TestCase):
    def setUp(self):
        self.clipper = Clipper()
        
        # We need a small mock video to test cutting and reframing
        self.test_dir = config.TEMP_MEDIA_DIR / "test_clipper"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.source_video = self.test_dir / "source.mp4"
        
        # Check if the source video exists from previous runs, if not create a dummy using ffmpeg
        if not self.source_video.exists():
            import subprocess
            # Generate a 5-second dummy mp4 video with audio
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=5:size=1920x1080:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                str(self.source_video)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_clip_metadata(self):
        meta = ClipMetadata(
            clip_id="test_clip_1",
            clip_path="path/to/clip.mp4",
            duration=30.0,
            moment_score=0.85,
            transcript="hello world",
            has_captions=True,
            emotion="joy"
        )
        self.assertEqual(meta.clip_id, "test_clip_1")
        self.assertEqual(meta.clip_path, "path/to/clip.mp4")
        self.assertEqual(meta.duration, 30.0)
        self.assertEqual(meta.moment_score, 0.85)
        self.assertEqual(meta.transcript, "hello world")
        self.assertTrue(meta.has_captions)
        self.assertEqual(meta.emotion, "joy")
        self.assertEqual(meta.title, "")
        self.assertFalse(meta.seo_ready)

    def test_seconds_to_ass_time(self):
        self.assertEqual(Clipper._seconds_to_ass_time(0.0), "0:00:00.00")
        self.assertEqual(Clipper._seconds_to_ass_time(65.123), "0:01:05.12")
        self.assertEqual(Clipper._seconds_to_ass_time(3665.5), "1:01:05.50")

    def test_generate_ass_captions(self):
        words = [
            TranscriptWord(word="Hello", start=0.5, end=1.0, probability=0.99),
            TranscriptWord(word="world", start=1.0, end=1.5, probability=0.98),
            TranscriptWord(word="this", start=1.5, end=2.0, probability=0.97),
            TranscriptWord(word="is", start=2.0, end=2.5, probability=0.96),
            TranscriptWord(word="testing", start=2.5, end=3.0, probability=0.95),
        ]
        segments = [
            TranscriptSegment(start=0.5, end=3.0, text="Hello world this is testing", words=words)
        ]
        
        ass_path = self.clipper._generate_ass_captions("test_ass_clip", segments)
        self.assertIsNotNone(ass_path)
        self.assertTrue(ass_path.exists())
        
        # Read file contents and check for formatting
        content = ass_path.read_text(encoding="utf-8")
        self.assertIn("Style: Default,Arial,48", content)
        self.assertIn("Dialogue:", content)
        
        # Clean up
        ass_path.unlink()

    def test_create_clip_successful(self):
        # Test full creation process with our dummy source video
        streamer = config.StreamerConfig(
            name="test_streamer",
            platform="twitch",
            channel="testchannel",
            url="https://twitch.tv/testchannel"
        )
        
        words = [
            TranscriptWord(word="Hello", start=0.5, end=1.0, probability=0.99),
            TranscriptWord(word="world", start=1.0, end=1.5, probability=0.98),
        ]
        segments = [
            TranscriptSegment(start=0.5, end=1.5, text="Hello world", words=words)
        ]
        
        clip_id = "test_create_clip_1"
        meta = self.clipper.create_clip(
            source_video=self.source_video,
            streamer=streamer,
            start_offset=1.0,
            duration=3,
            moment_score=0.9,
            transcript_segments=segments,
            emotion="joy",
            custom_clip_id=clip_id
        )
        
        self.assertIsNotNone(meta)
        self.assertEqual(meta.clip_id, clip_id)
        self.assertTrue(Path(meta.clip_path).exists())
        self.assertEqual(meta.duration, 3.0)
        self.assertEqual(meta.moment_score, 0.9)
        self.assertEqual(meta.emotion, "joy")
        self.assertEqual(meta.transcript, "Hello world")
        self.assertTrue(meta.has_captions)
        
        # Check metadata JSON exists
        json_path = config.CLIPS_DIR / f"{clip_id}.json"
        self.assertTrue(json_path.exists())
        
        # Clean up files created
        Path(meta.clip_path).unlink()
        json_path.unlink()

    def tearDown(self):
        # Cleanup test folder
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
