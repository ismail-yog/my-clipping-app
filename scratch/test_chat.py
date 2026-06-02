import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from detector.chat import ChatEvent, BaseChatMonitor, create_chat_monitor, TwitchChatMonitor, YouTubeChatMonitor, KickChatMonitor

class TestChatMonitor(unittest.TestCase):
    def setUp(self):
        # Create a test streamer config
        self.streamer_twitch = config.StreamerConfig(
            name="test_twitch",
            platform="twitch",
            channel="testchannel",
            url="https://twitch.tv/testchannel"
        )
        self.streamer_youtube = config.StreamerConfig(
            name="test_youtube",
            platform="youtube",
            channel="UC12345",
            url="https://youtube.com/channel/UC12345"
        )
        self.streamer_kick = config.StreamerConfig(
            name="test_kick",
            platform="kick",
            channel="testkick",
            url="https://kick.com/testkick"
        )

    def test_factory_creation(self):
        monitor_twitch = create_chat_monitor(self.streamer_twitch)
        self.assertIsInstance(monitor_twitch, TwitchChatMonitor)
        self.assertEqual(monitor_twitch.channel, "testchannel")

        monitor_youtube = create_chat_monitor(self.streamer_youtube)
        self.assertIsInstance(monitor_youtube, YouTubeChatMonitor)

        monitor_kick = create_chat_monitor(self.streamer_kick)
        self.assertIsInstance(monitor_kick, KickChatMonitor)

        # Test unsupported platform
        unsupported = config.StreamerConfig(
            name="test_invalid",
            platform="invalid",
            channel="invalid",
            url="https://invalid.com/invalid"
        )
        self.assertIsNone(create_chat_monitor(unsupported))

    def test_chat_event_dataclass(self):
        event = ChatEvent(
            timestamp=123456789.0,
            message_count=10,
            emote_count=5,
            event_type="burst",
            intensity=0.75
        )
        self.assertEqual(event.timestamp, 123456789.0)
        self.assertEqual(event.message_count, 10)
        self.assertEqual(event.emote_count, 5)
        self.assertEqual(event.event_type, "burst")
        self.assertEqual(event.intensity, 0.75)
        # Verify compatibility property
        self.assertEqual(event.score, 0.75)

    @patch('time.time')
    def test_sliding_window_and_burst_calculation(self, mock_time):
        mock_time.return_value = 1700000000.0
        # We subclass BaseChatMonitor to test abstract start/stop and message logic
        class MockMonitor(BaseChatMonitor):
            def start(self):
                self._running = True
            def stop(self):
                self._running = False

        monitor = MockMonitor(self.streamer_twitch)
        monitor.thresholds = config.DetectionThresholds(
            chat_msgs_per_sec=2.0,  # lower threshold for testing (20 msgs in 10s)
            chat_emote_multiplier=1.5
        )

        now = 1700000000.0
        
        # 1. Add messages below threshold (e.g., 10 messages in 10s -> 1 msg/sec)
        for i in range(10):
            monitor._on_message(now - 10 + i, is_emote_heavy=False)
        
        self.assertEqual(len(monitor.recent_events), 0, "Should not detect a burst when below threshold")

        # Clear events
        monitor.clear_events()

        # 2. Add messages above threshold (e.g., 30 messages in 10s -> 3 msgs/sec) without emotes
        # Emote count is 0
        for i in range(30):
            monitor._on_message(now - 10 + (i / 3.0), is_emote_heavy=False)
            
        self.assertGreater(len(monitor.recent_events), 0, "Should detect a burst when above threshold")
        last_event = monitor.recent_events[-1]
        self.assertEqual(last_event.event_type, "normal")

        # Clear events and message window
        monitor.clear_events()
        monitor._message_window = []

        # Let's test with messages above 5.0 (e.g., 60 messages in 10s -> 6 msgs/sec) to get type "burst"
        for i in range(60):
            monitor._on_message(now - 10 + (i / 6.0), is_emote_heavy=False)
        self.assertGreater(len(monitor.recent_events), 0)
        last_event = monitor.recent_events[-1]
        self.assertEqual(last_event.event_type, "burst")

        # Clear events and message window
        monitor.clear_events()
        monitor._message_window = []

        # 3. Add messages above threshold with emote-heavy (e.g., 30 messages, 15 are emote-heavy -> emote_ratio = 0.5)
        for i in range(30):
            is_emote = i % 2 == 0
            monitor._on_message(now - 10 + (i / 3.0), is_emote_heavy=is_emote)
            
        self.assertGreater(len(monitor.recent_events), 0)
        last_event = monitor.recent_events[-1]
        # Emote multiplier bonus (1.5x) should be applied since emote_ratio (0.5) > 0.3
        # Expected base intensity: 3.0 / 20.0 = 0.15
        # Expected multiplied intensity: 0.15 * 1.5 = 0.225
        self.assertAlmostEqual(last_event.intensity, 0.225)
        self.assertEqual(last_event.emote_count, 15)

    def test_reconnection_and_thread_safety(self):
        # Ensure start and stop work and create/join thread
        monitor = create_chat_monitor(self.streamer_twitch)
        
        # Mock the run_loop so it doesn't actually connect to WS
        with patch.object(monitor, "_run_loop") as mock_run_loop:
            monitor.start()
            self.assertTrue(monitor._running)
            self.assertIsNotNone(monitor._thread)
            
            monitor.stop()
            self.assertFalse(monitor._running)

if __name__ == "__main__":
    unittest.main()
