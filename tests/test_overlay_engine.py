"""
Unit Tests for OverlayEngine, Multi-line Emojis, and Platform Watermark Badges.
"""

import unittest
import tempfile
from pathlib import Path
from PIL import Image

from processor.overlay_engine import OverlayEngine, tokenize_text_with_emojis
from processor.captions_engine import CaptionsEngine, SubtitleStyle


class TestOverlayEngine(unittest.TestCase):

    def setUp(self):
        self.engine = OverlayEngine()

    def test_tokenization_with_emojis(self):
        text = "Neon was HYPED 😭💀 that DDG is back 🔥"
        tokens = tokenize_text_with_emojis(text)
        self.assertEqual(len(tokens), 4)
        # Check that emojis are flagged as is_emoji == True
        emoji_tokens = [tok for tok, is_em in tokens if is_em]
        self.assertIn("😭💀", emoji_tokens)
        self.assertIn("🔥", emoji_tokens)

    def test_white_canvas_overlay_rendering(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "white_overlay.png"
            res = self.engine.render_white_canvas_overlay(
                output_path=out_file,
                hook_text="Neon was HYPED that DDG is back on YT but says he is not DUB 😭💀",
                streamer_name="n3on",
                platform="kick"
            )
            self.assertTrue(res.exists())
            with Image.open(res) as img:
                self.assertEqual(img.size, (1080, 1920))
                self.assertEqual(img.mode, "RGBA")

    def test_platform_badges(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            for plat in ["kick", "twitch", "youtube"]:
                out_file = Path(tmp_dir) / f"{plat}_badge.png"
                res = self.engine.render_white_canvas_overlay(
                    output_path=out_file,
                    hook_text="TEST HEADLINE 🔥",
                    streamer_name="TestStreamer",
                    platform=plat
                )
                self.assertTrue(res.exists())

    def test_full_bleed_hook_banner(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "banner_overlay.png"
            res = self.engine.render_full_bleed_hook_banner(
                output_path=out_file,
                hook_text="BRO REALLY THOUGHT HE WAS HIM 😭💀",
                streamer_name="xqc"
            )
            self.assertTrue(res.exists())
            with Image.open(res) as img:
                self.assertEqual(img.size, (1080, 1920))
                self.assertEqual(img.mode, "RGBA")

    def test_captions_layout_margin_separation(self):
        captions_engine = CaptionsEngine()
        transcript = [
            {"start": 0.0, "end": 2.0, "text": "TERRIBLE BRO"}
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. White canvas layout -> MarginV should be 300
            white_ass = Path(tmp_dir) / "white.ass"
            captions_engine.generate_ass(
                clip_id="test_white",
                transcript_segments=transcript,
                output_path=white_ass,
                style=SubtitleStyle.HORMOZI,
                layout_type="white_canvas"
            )
            white_content = white_ass.read_text(encoding="utf-8")
            self.assertIn(",300,1", white_content)

            # 2. 9:16 full-bleed layout -> MarginV should be 420
            bleed_ass = Path(tmp_dir) / "bleed.ass"
            captions_engine.generate_ass(
                clip_id="test_bleed",
                transcript_segments=transcript,
                output_path=bleed_ass,
                style=SubtitleStyle.HORMOZI,
                layout_type="single_speaker"
            )
            bleed_content = bleed_ass.read_text(encoding="utf-8")
            self.assertIn(",420,1", bleed_content)


if __name__ == "__main__":
    unittest.main()
