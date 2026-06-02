import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import config
from uploader.youtube import YouTubeUploader, UploadResult


class TestYouTubeUploader(unittest.TestCase):
    def setUp(self):
        self.uploader = YouTubeUploader()
        self.test_dir = config.TEMP_MEDIA_DIR / "test_uploader"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.video_path = self.test_dir / "test_video.mp4"
        self.thumbnail_path = self.test_dir / "test_thumbnail.jpg"
        self.video_path.write_text("dummy video data")
        self.thumbnail_path.write_text("dummy thumbnail data")

    def tearDown(self):
        # Cleanup temp test files
        if self.video_path.exists():
            self.video_path.unlink()
        if self.thumbnail_path.exists():
            self.thumbnail_path.unlink()
        try:
            self.test_dir.rmdir()
        except Exception:
            pass

    @patch("google.oauth2.credentials.Credentials.from_authorized_user_file")
    @patch("googleapiclient.discovery.build")
    def test_get_authenticated_service_success(self, mock_build, mock_from_file):
        # Setup mocks
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_from_file.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        with patch("pathlib.Path.exists", return_value=True):
            service = self.uploader._get_authenticated_service()

        self.assertEqual(service, mock_service)
        mock_from_file.assert_called_once()
        mock_build.assert_called_once_with("youtube", "v3", credentials=mock_creds)

    @patch("google.oauth2.credentials.Credentials.from_authorized_user_file")
    @patch("google.auth.transport.requests.Request")
    @patch("googleapiclient.discovery.build")
    def test_get_authenticated_service_refresh(self, mock_build, mock_request, mock_from_file):
        # Setup creds that are expired but have a refresh token
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "some_refresh_token"
        mock_from_file.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.write_text") as mock_write:
            service = self.uploader._get_authenticated_service()

        self.assertEqual(service, mock_service)
        mock_creds.refresh.assert_called_once()
        mock_write.assert_called_once()
        mock_build.assert_called_once()

    @patch("database.Database.count_uploads_today")
    @patch("uploader.youtube.YouTubeUploader._get_authenticated_service")
    @patch("googleapiclient.http.MediaFileUpload")
    def test_upload_success(self, mock_media_file, mock_get_service, mock_count_uploads):
        # Setup quota check to pass
        mock_count_uploads.return_value = 0

        # Setup YouTube service mock response
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_insert = MagicMock()
        mock_service.videos.return_value.insert.return_value = mock_insert
        mock_insert.execute.return_value = {"id": "abcdef123"}

        res = self.uploader.upload(
            video_path=self.video_path,
            title="Cool clip!",
            description="Awesome moment",
            tags=["fun", "gaming"]
        )

        self.assertTrue(res.success)
        self.assertEqual(res.video_id, "abcdef123")
        self.assertEqual(res.video_url, "https://youtube.com/shorts/abcdef123")
        self.assertEqual(res.error, "")

        # Verify #Shorts was auto-appended to description
        snippet_body = mock_service.videos.return_value.insert.call_args[1]["body"]["snippet"]
        self.assertIn("#Shorts", snippet_body["description"])

    @patch("database.Database.count_uploads_today")
    def test_upload_quota_exceeded(self, mock_count_uploads):
        # Setup quota check to fail (daily limit is 6)
        mock_count_uploads.return_value = 6

        res = self.uploader.upload(
            video_path=self.video_path,
            title="Quota test",
            description="Should fail",
            tags=[]
        )

        self.assertFalse(res.success)
        self.assertIn("Daily upload quota reached", res.error)

    @patch("uploader.youtube.YouTubeUploader._get_authenticated_service")
    @patch("googleapiclient.http.MediaFileUpload")
    def test_set_thumbnail_success(self, mock_media_file, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_set = MagicMock()
        mock_service.thumbnails.return_value.set.return_value = mock_set
        mock_set.execute.return_value = {"url": "http://img.youtube.com/something.jpg"}

        success = self.uploader.set_thumbnail("abcdef123", self.thumbnail_path)
        self.assertTrue(success)
        mock_service.thumbnails.return_value.set.assert_called_once()


if __name__ == "__main__":
    unittest.main()
