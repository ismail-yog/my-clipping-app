"""
StreamClipper — Unit Tests for HookScorer Semantic Gate & Duration Enforcement
Verifies that:
1. Low-retention speech without punchlines is dumped immediately (score < 65).
2. High-retention speech produces candidates with score >= 65 and duration strictly between 30 and 45 seconds.
3. VODProcessor and StreamPipeline use HookScorer to discard acoustic false positives.
"""

import unittest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from processor.hook_scorer import HookScorer, HookCandidate
from processor.scorer import MomentScore
from database import Database
from task_queue import TaskQueue
from watcher.monitor import StreamStatus
from config import StreamerConfig


class TestHookScorerGate(unittest.TestCase):
    def setUp(self):
        self.scorer = HookScorer(min_hook_score=65)
        self.scorer.nvidia_api_key = ""
        self.scorer._ollama_disabled = True

    def test_low_retention_speech_rejected_by_semantic_gate(self):
        # Mundane, flat conversation lacking punchline or excitement
        mundane_segments = [
            {"start": 0.0, "end": 10.0, "text": "hello we are testing audio recording today"},
            {"start": 10.0, "end": 20.0, "text": "nothing much happening right now just walking"},
            {"start": 20.0, "end": 35.0, "text": "yeah that is pretty normal i guess"},
        ]
        candidate = self.scorer.evaluate_moment_buffer(
            transcript_segments=mundane_segments,
            streamer_name="TestStreamer",
            min_score=65,
        )
        self.assertIsNone(candidate, "Mundane speech without payoff must be rejected by semantic gate (<65%)")

    def test_viral_highlight_speech_approved_and_clamped(self):
        # High-intensity, emotionally charged speech with hype tokens
        hype_segments = [
            {"start": 0.0, "end": 8.0, "text": "BRO WAIT! NO WAY HE JUST DID THAT!"},
            {"start": 8.0, "end": 20.0, "text": "THIS IS THE MOST INSANE CLUTCH WTF! OMG!"},
            {"start": 20.0, "end": 36.0, "text": "ARE YOU SERIOUS RIGHT NOW?! GG THAT WAS UNBELIEVABLE!"},
        ]
        candidate = self.scorer.evaluate_moment_buffer(
            transcript_segments=hype_segments,
            streamer_name="TestStreamer",
            min_score=65,
        )
        self.assertIsNotNone(candidate, "High-intensity viral event must be approved (>= 65%)")
        self.assertGreaterEqual(candidate.hook_score, 65)
        # Duration must strictly be between 30 and 45 seconds
        self.assertGreaterEqual(candidate.duration_sec, 30.0)
        self.assertLessEqual(candidate.duration_sec, 45.0)
        self.assertTrue(len(candidate.title) > 0)
        self.assertTrue(len(candidate.hook_text) > 0)

    def test_score_transcript_duration_bounds(self):
        # Test long transcript slicing
        segments = [
            {"start": float(i * 5), "end": float(i * 5 + 5), "text": f"INSANE PLAY {i}! BRO CLUTCH!"}
            for i in range(20)
        ]
        candidates = self.scorer.score_transcript(
            transcript_segments=segments,
            streamer_name="KaiCenat",
            window_sec=40,
            step_sec=15,
        )
        self.assertTrue(len(candidates) > 0)
        for c in candidates:
            self.assertGreaterEqual(c.hook_score, 65)
            self.assertGreaterEqual(c.duration_sec, 30.0)
            self.assertLessEqual(c.duration_sec, 45.0)

    def test_lead_editorial_director_json_parsing_and_gate(self):
        # Verify JSON parsing of Lead Editorial output schema
        llm_response = """
```json
{
  "is_viral": true,
  "archetype": "The Plot Twist / Fail",
  "start_word": "Bro",
  "end_word": "WALL",
  "hook_overlay": "HE THOUGHT HE WAS HIM 💀",
  "retention_score": 9,
  "editorial_reasoning": "Instant overconfidence setup followed by immediate catastrophic failure and scream."
}
```
"""
        segments = [
            {
                "start": 0.0,
                "end": 35.0,
                "text": "Bro watch this headshot through the WALL",
                "words": [
                    {"word": "Bro", "start": 0.5, "end": 1.0},
                    {"word": "watch", "start": 1.1, "end": 1.5},
                    {"word": "this", "start": 1.6, "end": 2.0},
                    {"word": "WALL", "start": 32.0, "end": 33.5},
                ]
            }
        ]
        parsed = self.scorer._parse_llm_json(
            response=llm_response,
            window_text="Bro watch this headshot through the WALL",
            start_sec=0.0,
            end_sec=35.0,
            window_segments=segments,
        )
        self.assertEqual(len(parsed), 1)
        cand = parsed[0]
        self.assertEqual(cand.archetype, "The Plot Twist / Fail")
        self.assertEqual(cand.hook_score, 90)
        self.assertEqual(cand.start_ms, 500)
        self.assertEqual(cand.end_ms, 33500)
        self.assertEqual(cand.hook_text, "HE THOUGHT HE WAS HIM 💀")

    def test_lead_editorial_sub_8_gate_rejection(self):
        # Verify that retention_score < 8 is strictly rejected
        low_response = """
{
  "is_viral": true,
  "archetype": "Unfiltered Storytime",
  "start_word": "Okay",
  "end_word": "cool",
  "hook_overlay": "NICE TALK",
  "retention_score": 7,
  "editorial_reasoning": "Mildly interesting but lacks punchline."
}
"""
        parsed = self.scorer._parse_llm_json(
            response=low_response,
            window_text="Okay that was cool",
            start_sec=0.0,
            end_sec=30.0,
            window_segments=[],
        )
        self.assertEqual(len(parsed), 0, "Lead Editorial gate must reject score 7/10 (< 8/10)")


class TestVODHookScorerIntegration(unittest.TestCase):
    @patch("processor.hook_scorer.HookScorer._call_nvidia_nim", return_value=None)
    @patch("processor.hook_scorer.HookScorer._call_ollama", return_value=None)
    def test_vod_find_viral_moments_drops_sub_65(self, mock_ollama, mock_nim):
        from processor.vod import VODProcessor
        processor = VODProcessor(db=MagicMock())

        # Flat speech segments
        flat_segments = [
            {"start": 0.0, "end": 15.0, "text": "so we went to the store and bought some milk"},
            {"start": 15.0, "end": 35.0, "text": "then we drove back home and put it in the fridge"},
        ]
        moments = processor._find_viral_moments(flat_segments, duration=35.0)
        self.assertEqual(len(moments), 0, "VODProcessor must drop all sub-65% segments")

    @patch("processor.hook_scorer.HookScorer._call_nvidia_nim", return_value=None)
    @patch("processor.hook_scorer.HookScorer._call_ollama", return_value=None)
    def test_vod_find_viral_moments_keeps_high_scoring_candidates(self, mock_ollama, mock_nim):
        from processor.vod import VODProcessor
        processor = VODProcessor(db=MagicMock())

        viral_segments = [
            {"start": 0.0, "end": 10.0, "text": "BRO WATCH THIS! UNBELIEVABLE NO WAY WTF!"},
            {"start": 10.0, "end": 25.0, "text": "HE IS HACKING! INSANE CLUTCH OMG GG!"},
            {"start": 25.0, "end": 40.0, "text": "I AM SCREAMING BRO THAT WAS EPIC!"},
        ]
        moments = processor._find_viral_moments(viral_segments, duration=40.0)
        self.assertGreaterEqual(len(moments), 1)
        first = moments[0]
        self.assertGreaterEqual(first.hook_score, 65)
        self.assertGreaterEqual(first.duration_sec, 30.0)
        self.assertLessEqual(first.duration_sec, 45.0)


class TestPipelineSemanticGate(unittest.TestCase):
    @patch("pipeline.StreamCapture")
    @patch("pipeline.SentimentDetector")
    @patch("pipeline.Clipper")
    def test_pipeline_dumps_acoustic_trigger_when_speech_is_mundane(
        self, mock_clipper_cls, mock_sentiment_cls, mock_capture_cls
    ):
        from pipeline import StreamPipeline
        streamer = StreamerConfig(
            name="test_streamer",
            platform="twitch",
            channel="test_streamer",
            url="https://twitch.tv/test_streamer",
            enabled=True
        )
        status = StreamStatus(streamer=streamer)
        db = MagicMock()
        tq = MagicMock()

        pipeline = StreamPipeline(status=status, db=db, task_queue=tq)
        pipeline.hook_scorer.nvidia_api_key = ""
        pipeline.hook_scorer._ollama_disabled = True

        # Mock capture and sentiment detector
        pipeline.capture.get_concat_file.return_value = Path("dummy_buffer.mp4")
        pipeline.capture.extract_audio.return_value = Path("dummy_audio.wav")
        # Return mundane transcript that scores < 65%
        pipeline.sentiment_detector.transcribe.return_value = [
            {"start": 0.0, "end": 20.0, "text": "uh yeah so basically nothing is happening"},
            {"start": 20.0, "end": 40.0, "text": "just silent typing here ok cool"},
        ]

        # Trigger acoustic event with score 0.85
        moment = MomentScore(
            timestamp=time.time(),
            combined_score=0.85,
            audio_score=0.9,
            chat_score=0.2,
            sentiment_score=0.1,
            audio_events=[],
            chat_events=[],
            sentiment_events=[],
            reason="audio_spike",
        )
        pipeline._on_moment_triggered(moment)

        # Semantic gate should reject it and never call clipper.create_clip
        pipeline.clipper.create_clip.assert_not_called()
        db.save_clip.assert_not_called()

    @patch("pipeline.StreamCapture")
    @patch("pipeline.SentimentDetector")
    @patch("pipeline.Clipper")
    def test_pipeline_processes_and_clamps_when_semantic_gate_passes(
        self, mock_clipper_cls, mock_sentiment_cls, mock_capture_cls
    ):
        from pipeline import StreamPipeline
        streamer = StreamerConfig(
            name="test_streamer",
            platform="twitch",
            channel="test_streamer",
            url="https://twitch.tv/test_streamer",
            enabled=True
        )
        status = StreamStatus(streamer=streamer)
        db = MagicMock()
        tq = MagicMock()

        pipeline = StreamPipeline(status=status, db=db, task_queue=tq)
        pipeline.hook_scorer.nvidia_api_key = ""
        pipeline.hook_scorer._ollama_disabled = True

        pipeline.capture.get_concat_file.return_value = Path("dummy_buffer.mp4")
        pipeline.capture.extract_audio.return_value = Path("dummy_audio.wav")
        # Return high-retention viral speech
        pipeline.sentiment_detector.transcribe.return_value = [
            {"start": 0.0, "end": 10.0, "text": "BRO NO WAY! INSANE CLUTCH OMG!"},
            {"start": 10.0, "end": 35.0, "text": "HE JUST WON THE ENTIRE TOURNAMENT WTF GG!"},
        ]

        clip_mock = MagicMock()
        clip_mock.clip_id = "test_clip_1"
        clip_mock.clip_path = "test_clip.mp4"
        clip_mock.duration = 35.0
        clip_mock.moment_score = 0.88
        clip_mock.transcript = "BRO NO WAY! INSANE CLUTCH OMG!"
        clip_mock.has_captions = True
        pipeline.clipper.create_clip.return_value = clip_mock

        from processor.seo import SEOMetadata
        pipeline.seo.generate = MagicMock(return_value=SEOMetadata(
            title="INSANE CLUTCH",
            description="Test description",
            tags=["viral", "shorts"],
            hook_text="NO WAY HE WON",
            thumbnail_prompt="",
            generated_by="mock",
        ))
        pipeline.hook_renderer.apply = MagicMock(return_value=True)
        pipeline.thumbnail_gen.generate = MagicMock(return_value=Path("thumb.jpg"))

        moment = MomentScore(
            timestamp=time.time(),
            combined_score=0.85,
            audio_score=0.9,
            chat_score=0.8,
            sentiment_score=0.8,
            audio_events=[],
            chat_events=[],
            sentiment_events=[],
            reason="audio_spike+chat_burst",
        )
        pipeline._on_moment_triggered(moment)

        # Clipper should be called with duration strictly between 30 and 45 seconds
        pipeline.clipper.create_clip.assert_called_once()
        call_kwargs = pipeline.clipper.create_clip.call_args.kwargs
        self.assertGreaterEqual(call_kwargs["duration"], 30.0)
        self.assertLessEqual(call_kwargs["duration"], 45.0)
        self.assertGreaterEqual(call_kwargs["moment_score"], 0.65)


if __name__ == "__main__":
    unittest.main()
