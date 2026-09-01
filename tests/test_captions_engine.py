"""
Tests for CaptionsEngine Word-Level Karaoke, Styles, and JSON Timelines.
"""

from pathlib import Path
from processor.captions_engine import CaptionsEngine, SubtitleStyle, CaptionWord


def test_caption_word_duration_math():
    w = CaptionWord(word="CLUTCH", start_ms=1000, end_ms=1450, emoji="🔥")
    assert w.duration_cs == 45
    assert w.emoji == "🔥"


def test_parse_whisper_words_with_alignment():
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
    assert len(blocks) == 1
    assert len(blocks[0].words) == 4
    assert blocks[0].words[0].start_ms == 0
    assert blocks[0].words[0].end_ms == 500
    assert blocks[0].words[1].emoji == "🤯"
    assert blocks[0].words[2].emoji == "🔥"


def test_generate_ass_all_styles(tmp_path):
    engine = CaptionsEngine()
    transcript_segments = [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "STOP SCROLLING RIGHT NOW"
        }
    ]

    for style in [SubtitleStyle.HORMOZI, SubtitleStyle.MRBEAST, SubtitleStyle.NEON, SubtitleStyle.MINIMAL_CLEAN]:
        out_file = tmp_path / f"test_{style.value}.ass"
        res = engine.generate_ass(
            clip_id=f"test_{style.value}",
            transcript_segments=transcript_segments,
            output_path=out_file,
            style=style
        )
        assert res.exists()
        content = res.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "PlayResX: 1080" in content
        assert "PlayResY: 1920" in content
        assert "Dialogue:" in content


def test_generate_json_timeline():
    engine = CaptionsEngine()
    transcript_segments = [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "THIS IS A TEST"
        }
    ]

    timeline = engine.generate_json_timeline(transcript_segments, style=SubtitleStyle.HORMOZI)
    assert timeline["style"] == "hormozi"
    assert "blocks" in timeline
    assert len(timeline["blocks"]) >= 1
    assert "words" in timeline["blocks"][0]
