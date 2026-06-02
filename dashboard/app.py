"""
StreamClipper — Dashboard
Flask web app for monitoring and controlling the pipeline.
Provides REST API endpoints and a premium single-page frontend.
"""

import time
import json
import logging
from typing import Optional
from flask import Flask, render_template, jsonify, request, Response, send_from_directory

logger = logging.getLogger("streamclipper.dashboard")

_pipeline_manager = None
_database = None


def create_app(pipeline_manager=None, db=None):
    """Create the Flask dashboard app."""
    global _pipeline_manager, _database
    _pipeline_manager = pipeline_manager
    _database = db

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = "streamclipper-dashboard-key"

    # ── Pages ───────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_template("index.html")

    # ── API: Status ─────────────────────────────────────────────────────

    @app.route("/api/status")
    def api_status():
        """Return current system status and stats."""
        data = {
            "timestamp": time.time(),
            "streamers": [],
            "active_pipelines": 0,
            "stats": {},
            "queue": {},
        }

        # Database stats
        if _database:
            data["stats"] = _database.get_stats()

        # Live streamer status from monitor
        if _pipeline_manager and _pipeline_manager.monitor:
            statuses = _pipeline_manager.monitor.statuses
            for key, status in statuses.items():
                data["streamers"].append({
                    "name": status.streamer.name,
                    "platform": status.streamer.platform,
                    "channel": status.streamer.channel,
                    "is_live": status.is_live,
                    "title": status.title,
                    "game": status.game,
                    "viewer_count": status.viewer_count,
                    "last_checked": status.last_checked,
                })
            data["active_pipelines"] = len(_pipeline_manager.active_pipelines)

        # Queue stats
        if _pipeline_manager and _pipeline_manager.task_queue:
            data["queue"] = _pipeline_manager.task_queue.get_queue_stats()

        return jsonify(data)

    # ── API: Streamers ──────────────────────────────────────────────────

    @app.route("/api/streamers", methods=["GET"])
    def api_get_streamers():
        """Get all configured streamers."""
        if not _database:
            return jsonify({"streamers": []})
        streamers = _database.get_streamers()
        return jsonify({"streamers": streamers})

    @app.route("/api/streamers", methods=["POST"])
    def api_add_streamer():
        """Add a new streamer."""
        if not _database:
            return jsonify({"error": "Database not initialized"}), 500

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required = ["name", "platform", "channel", "url"]
        for field_name in required:
            if field_name not in data:
                return jsonify({"error": f"Missing field: {field_name}"}), 400

        try:
            sid = _database.add_streamer(
                name=data["name"],
                platform=data["platform"],
                channel=data["channel"],
                url=data["url"],
                enabled=data.get("enabled", True),
                auto_approve=data.get("auto_approve", False),
            )
            return jsonify({"id": sid, "message": "Streamer added"})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/streamers/<int:streamer_id>", methods=["PUT"])
    def api_update_streamer(streamer_id):
        """Update a streamer."""
        if not _database:
            return jsonify({"error": "Database not initialized"}), 500

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        _database.update_streamer(streamer_id, **data)
        return jsonify({"message": "Streamer updated"})

    @app.route("/api/streamers/<int:streamer_id>", methods=["DELETE"])
    def api_delete_streamer(streamer_id):
        """Delete a streamer."""
        if not _database:
            return jsonify({"error": "Database not initialized"}), 500

        _database.delete_streamer(streamer_id)
        return jsonify({"message": "Streamer deleted"})

    # ── API: Clips ──────────────────────────────────────────────────────

    @app.route("/api/clips")
    def api_clips():
        """Get clips with optional filters."""
        if not _database:
            return jsonify({"clips": []})

        status = request.args.get("status")
        streamer = request.args.get("streamer")
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))

        clips = _database.get_clips(
            status=status,
            streamer=streamer,
            limit=limit,
            offset=offset,
        )
        return jsonify({"clips": clips})

    @app.route("/api/clips/<clip_id>")
    def api_get_clip(clip_id):
        """Get a single clip."""
        if not _database:
            return jsonify({"error": "Not found"}), 404

        clip = _database.get_clip(clip_id)
        if not clip:
            return jsonify({"error": "Clip not found"}), 404

        return jsonify({"clip": clip})

    @app.route("/api/clips/<clip_id>/approve", methods=["POST"])
    def api_approve_clip(clip_id):
        """Approve a clip for upload."""
        if not _pipeline_manager:
            return jsonify({"error": "Pipeline manager not initialized"}), 500

        if _pipeline_manager.approve_clip(clip_id):
            return jsonify({"message": "Clip approved and queued for upload"})
        return jsonify({"error": "Failed to approve clip"}), 400

    @app.route("/api/clips/<clip_id>/reject", methods=["POST"])
    def api_reject_clip(clip_id):
        """Reject a clip."""
        if not _pipeline_manager:
            return jsonify({"error": "Pipeline manager not initialized"}), 500

        if _pipeline_manager.reject_clip(clip_id):
            return jsonify({"message": "Clip rejected"})
        return jsonify({"error": "Failed to reject clip"}), 400

    # ── API: Uploads ────────────────────────────────────────────────────

    @app.route("/api/uploads")
    def api_uploads():
        """Get upload history."""
        if not _database:
            return jsonify({"uploads": []})

        limit = int(request.args.get("limit", 50))
        uploads = _database.get_uploads(limit=limit)
        return jsonify({"uploads": uploads})

    # ── API: Jobs ───────────────────────────────────────────────────────

    @app.route("/api/jobs")
    def api_jobs():
        """Get job queue."""
        if not _database:
            return jsonify({"jobs": []})

        status = request.args.get("status")
        limit = int(request.args.get("limit", 50))
        jobs = _database.get_jobs(status=status, limit=limit)
        return jsonify({"jobs": jobs})

    # ── API: Scores ─────────────────────────────────────────────────────

    @app.route("/api/scores")
    def api_scores():
        """Return recent moment scores for visualization."""
        scores = []
        if _pipeline_manager:
            for key, pipeline in _pipeline_manager.active_pipelines.items():
                for s in pipeline.scorer.recent_scores[-50:]:
                    scores.append({
                        "timestamp": s.timestamp,
                        "audio": s.audio_score,
                        "chat": s.chat_score,
                        "sentiment": s.sentiment_score,
                        "combined": s.combined_score,
                        "triggered": s.triggered,
                        "streamer": pipeline.streamer.name,
                    })
        return jsonify({"scores": scores})

    # ── API: SSE Events ─────────────────────────────────────────────────

    @app.route("/api/events")
    def api_events():
        """SSE endpoint for real-time updates."""
        def event_stream():
            while True:
                time.sleep(2)
                data = {
                    "timestamp": time.time(),
                    "active": 0,
                    "clips": 0,
                    "uploads_today": 0,
                    "pending_review": 0,
                    "queue_pending": 0,
                }

                if _database:
                    stats = _database.get_stats()
                    data["clips"] = stats.get("total_clips", 0)
                    data["uploads_today"] = stats.get("uploads_today", 0)
                    data["pending_review"] = stats.get("pending_review", 0)

                if _pipeline_manager:
                    data["active"] = len(_pipeline_manager.active_pipelines)
                    if _pipeline_manager.task_queue:
                        q = _pipeline_manager.task_queue.get_queue_stats()
                        data["queue_pending"] = q.get("pending", 0)

                yield f"data: {json.dumps(data)}\n\n"

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app
