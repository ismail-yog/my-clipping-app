import os
import sys
import unittest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from server.main import app
from server.deps import set_dependencies, get_db, get_pipeline_manager, get_task_queue


class TestServerAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create mock core components
        cls.mock_db = MagicMock()
        cls.mock_pm = MagicMock()
        cls.mock_tq = MagicMock()

        # Inject mocks
        set_dependencies(cls.mock_db, cls.mock_pm, cls.mock_tq)
        cls.client = TestClient(app)

    def setUp(self):
        # Reset mocks before each test
        self.mock_db.reset_mock()
        self.mock_pm.reset_mock()
        self.mock_tq.reset_mock()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("timestamp", data)

    def test_get_stats(self):
        mock_stats = {"total_clips": 10, "pending_review": 3, "approved": 7}
        self.mock_db.get_stats.return_value = mock_stats

        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), mock_stats)
        self.mock_db.get_stats.assert_called_once()

    def test_get_streamers(self):
        mock_streamers = [{"id": 1, "name": "Kai Cenat", "platform": "twitch"}]
        self.mock_db.get_streamers.return_value = mock_streamers

        response = self.client.get("/api/streamers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), mock_streamers)
        self.mock_db.get_streamers.assert_called_once_with(enabled_only=False)

    def test_create_streamer_success(self):
        self.mock_db.get_streamers.return_value = []
        created_streamer = {
            "id": 5,
            "name": "Ninja",
            "platform": "youtube",
            "channel": "ninja",
            "url": "https://youtube.com/ninja",
            "enabled": 1,
            "auto_approve": 0
        }
        self.mock_db.add_streamer.return_value = 5
        self.mock_db.get_streamer.return_value = created_streamer

        payload = {
            "name": "Ninja",
            "platform": "youtube",
            "channel": "ninja",
            "url": "https://youtube.com/ninja",
            "auto_approve": False
        }
        response = self.client.post("/api/streamers", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), created_streamer)
        self.mock_db.add_streamer.assert_called_once_with(
            name="Ninja",
            platform="youtube",
            channel="ninja",
            url="https://youtube.com/ninja",
            enabled=True,
            auto_approve=False
        )

    def test_update_streamer(self):
        self.mock_db.get_streamer.return_value = {"id": 1, "name": "Kai Cenat"}
        self.mock_db.update_streamer.return_value = True

        payload = {"enabled": False, "auto_approve": True}
        response = self.client.patch("/api/streamers/1", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.mock_db.update_streamer.assert_called_once_with(1, enabled=0, auto_approve=1)

    def test_delete_streamer(self):
        self.mock_db.get_streamer.return_value = {"id": 1, "name": "Kai Cenat"}
        self.mock_db.delete_streamer.return_value = True

        response = self.client.delete("/api/streamers/1")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.mock_db.delete_streamer.assert_called_once_with(1)

    def test_get_clips(self):
        mock_clips = [{"clip_id": "clip1", "title": "Viral Moment"}]
        self.mock_db.get_clips.return_value = mock_clips

        response = self.client.get("/api/clips?status=approved&limit=10&offset=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), mock_clips)
        self.mock_db.get_clips.assert_called_once_with(status="approved", streamer=None, limit=10, offset=5)

    def test_get_clip_by_id(self):
        mock_clip = {"clip_id": "clip1", "title": "Viral Moment"}
        self.mock_db.get_clip.return_value = mock_clip

        response = self.client.get("/api/clips/clip1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), mock_clip)
        self.mock_db.get_clip.assert_called_once_with("clip1")

    def test_approve_clip_success(self):
        self.mock_pm.approve_clip.return_value = True

        response = self.client.post("/api/clips/clip1/approve")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.mock_pm.approve_clip.assert_called_once_with("clip1")

    def test_delete_clip(self):
        self.mock_db.get_clip.return_value = {"clip_id": "clip1"}
        self.mock_db.delete_clip.return_value = True

        response = self.client.delete("/api/clips/clip1")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.mock_db.delete_clip.assert_called_once_with("clip1")

    def test_get_uploads(self):
        mock_uploads = [{"id": 1, "clip_id": "clip1", "video_id": "vid1"}]
        self.mock_db.get_uploads.return_value = mock_uploads

        response = self.client.get("/api/uploads?limit=15")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), mock_uploads)
        self.mock_db.get_uploads.assert_called_once_with(limit=15)

    def test_process_vod_success(self):
        self.mock_tq.submit.return_value = 101

        payload = {"url": "https://youtube.com/watch?v=vod1", "layout_type": "gamer"}
        response = self.client.post("/api/vod/process", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "101")
        self.mock_tq.submit.assert_called_once_with(
            job_type="vod_process",
            payload={"url": "https://youtube.com/watch?v=vod1", "layout_type": "gamer"},
            priority=2
        )

    def test_get_jobs(self):
        mock_jobs = [{"id": 101, "status": "pending"}]
        self.mock_db.get_jobs.return_value = mock_jobs

        response = self.client.get("/api/jobs?status=pending&limit=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), mock_jobs)
        self.mock_db.get_jobs.assert_called_once_with(status="pending", limit=5)


if __name__ == "__main__":
    unittest.main()
