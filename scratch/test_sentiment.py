import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from detector.sentiment import TranscriptWord, TranscriptSegment, SentimentEvent, SentimentDetector

class TestSentimentDetector(unittest.TestCase):
    def setUp(self):
        self.detector = SentimentDetector()
        self.detector.thresholds = config.DetectionThresholds(
            sentiment_min_confidence=0.6,
            sentiment_emotions=["joy", "anger", "surprise"],
            sentiment_weight=0.3
        )

    def test_dataclasses(self):
        word = TranscriptWord(word="test", start=1.0, end=1.5, probability=0.99)
        self.assertEqual(word.word, "test")
        self.assertEqual(word.start, 1.0)
        self.assertEqual(word.end, 1.5)
        self.assertEqual(word.probability, 0.99)

        seg = TranscriptSegment(start=1.0, end=2.0, text="test sentence", words=[word])
        self.assertEqual(seg.start, 1.0)
        self.assertEqual(seg.end, 2.0)
        self.assertEqual(seg.text, "test sentence")
        self.assertEqual(seg.words[0], word)

        event = SentimentEvent(
            timestamp=123456789.0,
            emotion="joy",
            confidence=0.85,
            text_snippet="amazing day"
        )
        self.assertEqual(event.timestamp, 123456789.0)
        self.assertEqual(event.emotion, "joy")
        self.assertEqual(event.confidence, 0.85)
        self.assertEqual(event.text_snippet, "amazing day")
        # Test score property compatibility
        self.assertEqual(event.score, 0.85)

    @patch('time.time')
    @patch('detector.sentiment.SentimentDetector._load_whisper')
    @patch('detector.sentiment.SentimentDetector._load_sentiment_pipeline')
    def test_analyze_and_threshold_filtering(self, mock_load_sentiment, mock_load_whisper, mock_time):
        mock_time.return_value = 1000.0
        # Setup mocks
        mock_whisper = MagicMock()
        mock_load_whisper.return_value = mock_whisper
        
        # Whisper transcribe returns segments with text and words
        mock_seg = MagicMock()
        mock_seg.text = "I am so happy and excited!"
        mock_seg.start = 1.0
        mock_seg.end = 3.0
        
        mock_word = MagicMock()
        mock_word.word = "happy"
        mock_word.start = 1.5
        mock_word.end = 2.0
        mock_word.probability = 0.98
        mock_seg.words = [mock_word]
        
        mock_whisper.transcribe.return_value = ([mock_seg], None)

        mock_sentiment = MagicMock()
        mock_load_sentiment.return_value = mock_sentiment

        # 1. Test target emotion above threshold -> Should create event
        mock_sentiment.return_value = [[{"label": "joy", "score": 0.85}]]
        
        events = self.detector.analyze(Path("dummy.wav"), reference_time=1000.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].emotion, "joy")
        self.assertEqual(events[0].confidence, 0.85)
        self.assertEqual(events[0].text_snippet, "I am so happy and excited!")
        self.assertEqual(events[0].timestamp, 1001.0)

        # Verify it was added to recent_events
        self.assertEqual(len(self.detector.recent_events), 1)

        # 2. Test target emotion but below confidence threshold (min=0.6) -> Should not create event
        self.detector.clear_events()
        mock_sentiment.return_value = [[{"label": "joy", "score": 0.45}]]
        
        events = self.detector.analyze(Path("dummy.wav"), reference_time=1000.0)
        self.assertEqual(len(events), 0)
        self.assertEqual(len(self.detector.recent_events), 0)

        # 3. Test non-target emotion (e.g. sadness) -> Should not create event
        self.detector.clear_events()
        mock_sentiment.return_value = [[{"label": "sadness", "score": 0.85}]]
        
        events = self.detector.analyze(Path("dummy.wav"), reference_time=1000.0)
        self.assertEqual(len(events), 0)

    @patch('time.time')
    def test_pruning(self, mock_time):
        mock_time.return_value = 1000.0
        
        event1 = SentimentEvent(timestamp=995.0, emotion="joy", confidence=0.8, text_snippet="snip1")
        event2 = SentimentEvent(timestamp=930.0, emotion="surprise", confidence=0.7, text_snippet="snip2")
        
        self.detector.recent_events = [event1, event2]
        
        # Pruning should remove event2 (timestamp 930.0 is more than 60s older than 1000.0)
        self.detector._prune_old_events()
        self.assertEqual(len(self.detector.recent_events), 1)
        self.assertEqual(self.detector.recent_events[0].text_snippet, "snip1")

        # Test get_recent_events for last 10s (should return event1)
        recent = self.detector.get_recent_events(last_n_seconds=10.0)
        self.assertEqual(len(recent), 1)

        # Test get_recent_events for last 3s (should return empty list since 995.0 is 5s older than 1000.0)
        recent_3s = self.detector.get_recent_events(last_n_seconds=3.0)
        self.assertEqual(len(recent_3s), 0)

if __name__ == "__main__":
    unittest.main()
