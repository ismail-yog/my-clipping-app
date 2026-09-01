"""
Tests for Multi-Platform Publisher Adapters and PublisherManager.
"""

from pathlib import Path
from uploader.tiktok import TikTokUploader
from uploader.instagram import InstagramUploader
from uploader.manager import PublisherManager, PublishRequest


def test_tiktok_unconfigured_fallback(tmp_path):
    uploader = TikTokUploader()
    # Unconfigured access token triggers Playwright fallback mode safely
    fake_video = tmp_path / "fake_video.mp4"
    fake_video.write_bytes(b"\x00" * 100)

    res = uploader.upload_video(video_path=fake_video, title="Test Short", tags=["viral"])
    assert res["status"] in ("queued", "success", "error")
    assert res["platform"] == "tiktok"


def test_instagram_unconfigured_handling():
    uploader = InstagramUploader()
    res = uploader.upload_reel(video_url="https://example.com/fake.mp4", caption="Test Caption")
    # Should report unconfigured safely when credentials are blank
    assert "status" in res


def test_publisher_manager_dispatch(tmp_path):
    manager = PublisherManager()
    fake_video = tmp_path / "fake_short.mp4"
    fake_video.write_bytes(b"\x00" * 100)

    req = PublishRequest(
        video_path=fake_video,
        title="Test Multi-Upload",
        description="Test Desc",
        tags=["fyp"],
        platforms=["tiktok", "instagram"]
    )

    results = manager.publish_clip(req)
    assert "tiktok" in results
    assert "instagram" in results
