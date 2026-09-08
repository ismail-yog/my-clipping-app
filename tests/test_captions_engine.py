"""
Tests for CaptionsEngine Word-Level Karaoke, Styles, Normalization, and JSON Timelines.
"""

import unittest
import tempfile
from pathlib import Path
from processor.captions_engine import CaptionsEngine, SubtitleStyle, CaptionWord, normalize_subtitle_style


class TestCaptionsEngine(unittest.TestCase):

    def test_caption_word_duration_math(self):
        w = CaptionWord(word="CLUTCH", start_ms=1000, end_ms=1450, emoji="🔥")
        self.assertEqual(w.duration_cs, 45)
        self.assertEqual(w.emoji, "🔥")

    def test_normalize_subtitle_style(self):
        # Direct canonical enum
        self.assertEqual(normalize_subtitle_style(SubtitleStyle.MRBEAST), SubtitleStyle.MRBEAST)
        self.assertEqual(normalize_subtitle_style("mrbeast"), SubtitleStyle.MRBEAST)
        self.assertEqual(normalize_subtitle_style("glacier_glow"), SubtitleStyle.GLACIER_GLOW)
        self.assertEqual(normalize_subtitle_style("hormozi"), SubtitleStyle.HORMOZI)
        self.assertEqual(normalize_subtitle_style("neon"), SubtitleStyle.NEON)
        self.assertEqual(normalize_subtitle_style("tiktok_bold"), SubtitleStyle.TIKTOK_BOLD)
        self.assertEqual(normalize_subtitle_style("minimal_clean"), SubtitleStyle.MINIMAL_CLEAN)

        # Aliases from frontend & legacy configs
        self.assertEqual(normalize_subtitle_style("harmazi_yellow"), SubtitleStyle.HORMOZI)
        self.assertEqual(normalize_subtitle_style("hormozi_yellow"), SubtitleStyle.HORMOZI)
        self.assertEqual(normalize_subtitle_style("neon_cyber"), SubtitleStyle.NEON)
        self.assertEqual(normalize_subtitle_style("clean_sans"), SubtitleStyle.MINIMAL_CLEAN)
        self.assertEqual(normalize_subtitle_style("minimal"), SubtitleStyle.MINIMAL_CLEAN)
        self.assertEqual(normalize_subtitle_style("mr_beast"), SubtitleStyle.MRBEAST)
        self.assertEqual(normalize_subtitle_style("tiktok"), SubtitleStyle.TIKTOK_BOLD)

        # Unknown / None fallback
        self.assertEqual(normalize_subtitle_style("unknown_style"), SubtitleStyle.GLACIER_GLOW)
        self.assertEqual(normalize_subtitle_style(None), SubtitleStyle.GLACIER_GLOW)

    def test_parse_whisper_words_with_alignment(self):
        engine = CaptionsEngine()
        transcript_segments = [
            {
                "start": 1.0,
                "end": 3.0,
                "words": [
                    {"word": "OMG", "start": 1.0, "end": 1.5},
                    {"word": "INSANE", "start": 1.5, "end": 2.0},
                    {"word": "CLUTCH", "start": 2.0, "end": 2.5},
                    {"word": "BRO", "start": 2.5, "end": 3.0},
                ]
            }
        ]

        blocks = engine.parse_whisper_words(transcript_segments, base_offset_ms=1000, words_per_group=4)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(blocks[0].words), 4)
        self.assertEqual(blocks[0].words[0].start_ms, 0)
        self.assertEqual(blocks[0].words[0].end_ms, 500)
        self.assertEqual(blocks[0].words[1].emoji, "🤯")
        self.assertEqual(blocks[0].words[2].emoji, "🔥")

    def test_generate_ass_all_styles(self):
        engine = CaptionsEngine()
        transcript_segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "STOP SCROLLING RIGHT NOW"
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for style in [
                SubtitleStyle.GLACIER_GLOW,
                SubtitleStyle.HORMOZI,
                SubtitleStyle.MRBEAST,
                SubtitleStyle.NEON,
                SubtitleStyle.TIKTOK_BOLD,
                SubtitleStyle.MINIMAL_CLEAN,
                "harmazi_yellow",
                "neon_cyber",
                "clean_sans",
            ]:
                out_file = tmp_path / f"test_{style}.ass"
                res = engine.generate_ass(
                    clip_id=f"test_{style}",
                    transcript_segments=transcript_segments,
                    output_path=out_file,
                    style=style
                )
                self.assertTrue(res.exists())
                content = res.read_text(encoding="utf-8")
                self.assertIn("[Script Info]", content)
                self.assertIn("PlayResX: 1080", content)
                self.assertIn("PlayResY: 1920", content)
                self.assertIn("Dialogue:", content)

    def test_generate_json_timeline(self):
        engine = CaptionsEngine()
        transcript_segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "THIS IS A TEST"
            }
        ]

        timeline = engine.generate_json_timeline(transcript_segments, style=SubtitleStyle.HORMOZI)
        self.assertEqual(timeline["style"], "hormozi")
        self.assertIn("blocks", timeline)
        self.assertGreaterEqual(len(timeline["blocks"]), 1)
        self.assertIn("words", timeline["blocks"][0])


if __name__ == "__main__":
    unittest.main()
