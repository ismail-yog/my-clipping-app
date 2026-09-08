"""
Unit Tests for:
1. Profanity & Demonetization Censor Engine (subtitles, hooks, metadata)
2. Streamer platform brand colors in overlays (Kick, Twitch, YouTube, TikTok)
3. Bold high-contrast subtitle style headers
4. Dynamic editing jump-zoom punch-in filtergraphs
"""

import unittest
import tempfile
from pathlib import Path
from PIL import Image

from processor.censor import censor_word, censor_text, contains_profanity
from processor.captions_engine import CaptionsEngine, SubtitleStyle
from processor.overlay_engine import OverlayEngine, PLATFORM_COLORS
from processor.smart_crop import SmartCrop


class TestDynamicCensorStyles(unittest.TestCase):

    def test_censor_word(self):
        # Case preservation
        self.assertEqual(censor_word("fuck"), "f**k")
        self.assertEqual(censor_word("FUCKING"), "F***ING")
        self.assertEqual(censor_word("Bitch!"), "B***h!")
        self.assertEqual(censor_word("bullshit."), "bullsh*t.")
        self.assertEqual(censor_word("clean_word"), "clean_word")

    def test_censor_text(self):
        sample = "What the fuck is this shit bro? Don't be a bitch!"
        censored = censor_text(sample)
        self.assertNotIn("fuck", censored.lower())
        self.assertNotIn("shit", censored.lower())
        self.assertNotIn("bitch", censored.lower())
        self.assertIn("f**k", censored.lower())
        self.assertIn("sh*t", censored.lower())
        self.assertIn("b***h", censored.lower())

    def test_captions_engine_censoring(self):
        captions_engine = CaptionsEngine()
        transcript = [
            {"start": 0.0, "end": 2.0, "text": "This is fucking insane bro holy shit"}
        ]
        blocks = captions_engine.parse_whisper_words(transcript)
        words = [cw.word for b in blocks for cw in b.words]
        
        # Verify no raw profanities exist in parsed words
        self.assertIn("F***ING", [w.upper() for w in words])
        self.assertIn("SH*T", [w.upper() for w in words])
        self.assertNotIn("FUCKING", [w.upper() for w in words])
        self.assertNotIn("SHIT", [w.upper() for w in words])

    def test_subtitle_style_headers_and_fonts(self):
        for style in [SubtitleStyle.GLACIER_GLOW, SubtitleStyle.HORMOZI, SubtitleStyle.MRBEAST, SubtitleStyle.NEON]:
            header = CaptionsEngine.STYLE_HEADERS[style]
            # Ensure ultra-bold native Windows fonts are used
            self.assertTrue("Impact" in header or "Arial Black" in header or "Segoe UI" in header)
            # Ensure heavy outline is present
            self.assertIn("Outline", header)

    def test_platform_brand_colors(self):
        self.assertIn("kick", PLATFORM_COLORS)
        self.assertIn("twitch", PLATFORM_COLORS)
        self.assertIn("youtube", PLATFORM_COLORS)
        self.assertIn("tiktok", PLATFORM_COLORS)

        # Kick Neon Green
        self.assertEqual(PLATFORM_COLORS["kick"]["text"], (83, 252, 24, 255))
        # Twitch Signature Purple
        self.assertEqual(PLATFORM_COLORS["twitch"]["text"], (169, 112, 255, 255))
        # YouTube Red
        self.assertEqual(PLATFORM_COLORS["youtube"]["text"], (255, 59, 48, 255))
        # TikTok Cyan
        self.assertEqual(PLATFORM_COLORS["tiktok"]["text"], (0, 242, 254, 255))

    def test_overlay_rendering_with_censored_hook_and_platform_colors(self):
        engine = OverlayEngine()
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "test_overlay.png"
            res = engine.render_white_canvas_overlay(
                output_path=out_file,
                hook_text="WHAT THE FUCK BRO NO WAY 💀",
                streamer_name="KaiCenat",
                platform="twitch"
            )
            self.assertTrue(res.exists())
            with Image.open(res) as img:
                self.assertEqual(img.size, (1080, 1920))

    def test_dynamic_editing_filter(self):
        smart_crop = SmartCrop()
        fake_video = Path("fake_path.mp4")

        # White canvas with dynamic editing
        wc_dynamic = smart_crop.get_crop_filter(fake_video, start_sec=0.0, layout_type="white_canvas", dynamic_editing=True)
        self.assertIn("between(mod(t,7),3.5,7)", wc_dynamic)

        # White canvas without dynamic editing
        wc_static = smart_crop.get_crop_filter(fake_video, start_sec=0.0, layout_type="white_canvas", dynamic_editing=False)
        self.assertNotIn("between(mod(t,7),3.5,7)", wc_static)

        # Basic with dynamic editing
        basic_dynamic = smart_crop.get_crop_filter(fake_video, start_sec=0.0, layout_type="basic", dynamic_editing=True)
        self.assertIn("between(mod(t,7),3.5,7)", basic_dynamic)


if __name__ == "__main__":
    unittest.main()
