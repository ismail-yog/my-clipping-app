import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from processor.scorer import MomentScore, Scorer
from detector.audio import AudioEvent
from detector.chat import ChatEvent
from detector.sentiment import SentimentEvent

class TestScorer(unittest.TestCase):
    def setUp(self):
        self.thresholds = config.DetectionThresholds(
            audio_weight=0.3,
            chat_weight=0.4,
            sentiment_weight=0.3,
            moment_threshold=0.65,
            cooldown_seconds=120.0
        )
        self.trigger_calls = []
        self.on_trigger = lambda moment: self.trigger_calls.append(moment)
        self.scorer = Scorer(on_trigger=self.on_trigger, thresholds=self.thresholds)

    def test_moment_score_dataclass(self):
        moment = MomentScore(
            timestamp=12345.6,
            combined_score=0.75,
            audio_score=0.5,
            chat_score=0.8,
            sentiment_score=0.6,
            audio_events=[],
            chat_events=[],
            sentiment_events=[],
            reason="audio_spike+chat_burst",
            triggered=True
        )
        self.assertEqual(moment.timestamp, 12345.6)
        self.assertEqual(moment.combined_score, 0.75)
        self.assertEqual(moment.audio_score, 0.5)
        self.assertEqual(moment.chat_score, 0.8)
        self.assertEqual(moment.sentiment_score, 0.6)
        self.assertEqual(moment.reason, "audio_spike+chat_burst")
        self.assertTrue(moment.triggered)

    @patch('time.time')
    def test_scoring_and_triggering(self, mock_time):
        mock_time.return_value = 1700000000.0
        now = 1700000000.0

        # Simulate events
        audio_events = [
            AudioEvent(timestamp=now - 5, event_type="spike", intensity=0.9, db_level=-10.0)
        ]
        chat_events = [
            ChatEvent(timestamp=now - 2, message_count=30, emote_count=5, event_type="burst", intensity=0.8)
        ]
        sentiment_events = [
            SentimentEvent(timestamp=now - 1, emotion="joy", confidence=0.7, text_snippet="awesome")
        ]

        # Calculate expected scores:
        # audio_score = 0.9, chat_score = 0.8, sentiment_score = 0.7
        # combined = 0.9*0.3 + 0.8*0.4 + 0.7*0.3 = 0.27 + 0.32 + 0.21 = 0.8
        # Since active_signals >= 3 (all scores > 0.3), combined score gets a 1.25x boost!
        # combined * 1.25 = 0.8 * 1.25 = 1.0 (min(1.0, 1.0) = 1.0)
        
        moment = self.scorer.score_moment(audio_events, chat_events, sentiment_events)
        self.assertTrue(moment.triggered)
        self.assertEqual(moment.combined_score, 1.0)
        self.assertEqual(moment.audio_score, 0.9)
        self.assertEqual(moment.chat_score, 0.8)
        self.assertEqual(moment.sentiment_score, 0.7)
        self.assertEqual(len(self.trigger_calls), 1)
        self.assertEqual(self.trigger_calls[0], moment)

        # Confirm reason contains relevant descriptors
        self.assertIn("audio_spike", moment.reason)
        self.assertIn("chat_burst", moment.reason)
        self.assertIn("sentiment_joy", moment.reason)

    @patch('time.time')
    def test_cooldown_prevention(self, mock_time):
        mock_time.return_value = 1700000000.0
        now = 1700000000.0

        audio_events = [AudioEvent(timestamp=now - 2, event_type="spike", intensity=0.9, db_level=-10.0)]
        chat_events = [ChatEvent(timestamp=now - 2, message_count=30, emote_count=5, event_type="burst", intensity=0.9)]
        sentiment_events = []

        def get_events():
            t = mock_time.return_value
            ae = [AudioEvent(timestamp=t - 2, event_type="spike", intensity=0.9, db_level=-10.0)]
            ce = [ChatEvent(timestamp=t - 2, message_count=30, emote_count=5, event_type="burst", intensity=0.9)]
            return ae, ce, []

        # First trigger
        ae, ce, se = get_events()
        moment1 = self.scorer.score_moment(ae, ce, se)
        self.assertTrue(moment1.triggered)
        self.assertEqual(len(self.trigger_calls), 1)

        # Move forward by 30 seconds (less than 120s cooldown)
        mock_time.return_value = now + 30.0
        ae, ce, se = get_events()
        moment2 = self.scorer.score_moment(ae, ce, se)
        self.assertFalse(moment2.triggered, "Should not trigger because it is in cooldown")
        self.assertEqual(len(self.trigger_calls), 1)

        # Reset cooldown manually
        self.scorer.reset_cooldown()
        ae, ce, se = get_events()
        moment3 = self.scorer.score_moment(ae, ce, se)
        self.assertTrue(moment3.triggered, "Should trigger after manual cooldown reset")
        self.assertEqual(len(self.trigger_calls), 2)

        # Move forward by 130 seconds (exceeding 120s cooldown)
        mock_time.return_value = now + 30.0 + 130.0
        ae, ce, se = get_events()
        moment4 = self.scorer.score_moment(ae, ce, se)
        self.assertTrue(moment4.triggered, "Should trigger after cooldown window elapsed")
        self.assertEqual(len(self.trigger_calls), 3)

if __name__ == "__main__":
    unittest.main()
