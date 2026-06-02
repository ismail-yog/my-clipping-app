"""
StreamClipper — Main Entry Point
CLI that orchestrates the full autonomous pipeline.

Usage:
    python main.py                  # Run in production mode
    python main.py --test-mode      # Run against a sample VOD
    python main.py --dashboard-only # Run just the API + frontend
    python main.py --check          # Validate config and exit
"""

import sys
import time
import signal
import logging
import argparse
import threading

import config
from database import Database
from task_queue import TaskQueue
from pipeline import PipelineManager

logger = logging.getLogger("streamclipper.main")

# ── Global state for graceful shutdown ──────────────────────────────────────
_shutdown_event = threading.Event()


def signal_handler(signum, frame):
    logger.info("Shutdown signal received (sig=%d)", signum)
    _shutdown_event.set()


def parse_args():
    parser = argparse.ArgumentParser(
        description="StreamClipper — Autonomous stream highlight clipper & uploader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    Run the full pipeline
  python main.py --check            Validate config and exit
  python main.py --dashboard-only   Run the API server only
  python main.py --test-mode        Process a sample VOD (no live required)
        """,
    )
    parser.add_argument("--check", action="store_true", help="Validate configuration and exit")
    parser.add_argument("--test-mode", action="store_true", help="Run in test mode with a sample VOD")
    parser.add_argument("--dashboard-only", action="store_true", help="Run only the API server")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable the API server")
    parser.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--poll-interval", type=int, default=60, help="Seconds between live-status polls (default: 60)")
    parser.add_argument("--api-port", type=int, default=8000, help="FastAPI server port (default: 8000)")
    return parser.parse_args()


def check_config():
    """Validate configuration and print status."""
    print("\n+--------------------------------------------------+")
    print("|          StreamClip AI -- Config Check            |")
    print("+--------------------------------------------------+\n")

    warnings = config.validate_config()

    streamers = config.get_streamers()
    print(f"  Streamers configured: {len(config.DEFAULT_STREAMERS)}")
    print(f"  Streamers enabled:    {len(streamers)}")
    for s in streamers:
        print(f"    - {s.name} ({s.platform}) -- {s.url}")

    print(f"\n  Ollama host: {config.OLLAMA_HOST}")
    print(f"  Ollama model: {config.OLLAMA_MODEL}")
    print(f"  Whisper model: {config.WHISPER_MODEL}")
    print(f"  Whisper device: {config.WHISPER_DEVICE}")
    print(f"  Database: {config.DATABASE_PATH}")
    print(f"  Clips dir: {config.CLIPS_DIR}")

    if warnings:
        print(f"\n  [!] Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("\n  [OK] All checks passed!")

    # System dependencies
    print("\n  System dependencies:")
    import shutil
    for dep in ["ffmpeg", "streamlink", "ollama"]:
        path = shutil.which(dep)
        print(f"    {'[OK]' if path else '[X]'} {dep}: {path or 'NOT FOUND'}")

    # Database
    print("\n  Database:")
    try:
        db = Database()
        stats = db.get_stats()
        print(f"    [OK] SQLite connected")
        print(f"    Total clips: {stats['total_clips']}")
        print(f"    Total uploads: {stats['total_uploads']}")
        print(f"    Streamers: {stats['total_streamers']}")
        db.close()
    except Exception as e:
        print(f"    [X] Database error: {e}")

    print()


def start_api_server(pipeline_manager: PipelineManager, db: Database, task_queue: TaskQueue, port: int = 8000):
    """Start the FastAPI server in a background thread."""
    try:
        import uvicorn
        from server.main import create_app
        from server.deps import set_dependencies

        set_dependencies(db, pipeline_manager, task_queue)
        app = create_app()

        def run_server():
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        logger.info("FastAPI server running at http://0.0.0.0:%d", port)
        logger.info("API docs at http://localhost:%d/docs", port)
        return thread
    except Exception as e:
        logger.error("Failed to start FastAPI server: %s", e)
        return None


def run_test_mode(db: Database):
    """Run the pipeline against a sample VOD for testing."""
    logger.info("=== TEST MODE ===")

    from processor.seo import SEOGenerator
    seo = SEOGenerator()

    seo_result = seo.generate(
        transcript="This is a test transcript for the StreamClipper pipeline.",
        streamer_name="test_streamer",
        emotion="joy",
        platform="kick",
    )

    logger.info("Test SEO Title: %s", seo_result.title)
    logger.info("Test SEO Tags: %s", seo_result.tags)
    logger.info("Test SEO Hook: %s", seo_result.hook_text)
    logger.info("Test SEO Method: %s", seo_result.generated_by)
    logger.info("Database stats: %s", db.get_stats())
    logger.info("=== Test mode complete ===")


def main():
    args = parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print()
    print("  +-------------------------------------------+")
    print("  |     StreamClip AI v2.0                    |")
    print("  |     Autonomous Highlight Clipper           |")
    print("  |     Zero-Cost - Local AI - Auto Upload     |")
    print("  +-------------------------------------------+")
    print()

    if args.check:
        check_config()
        return

    # Initialize core services
    db = Database()
    task_queue = TaskQueue(db, poll_interval=config.QUEUE_POLL_INTERVAL)

    if args.test_mode:
        run_test_mode(db)
        return

    warnings = config.validate_config()
    for w in warnings:
        logger.warning(w)

    streamers = config.get_streamers()
    if not streamers and not args.dashboard_only:
        logger.error(
            "No streamers configured! Edit config.py or add via dashboard."
        )
        sys.exit(1)

    manager = PipelineManager(db, task_queue)

    # Start FastAPI server
    if not args.no_dashboard:
        start_api_server(manager, db, task_queue, port=args.api_port)

    if args.dashboard_only:
        task_queue.start()
        logger.info("Running in API-only mode. Frontend at http://localhost:3000")
        logger.info("Press Ctrl+C to exit.")
        _shutdown_event.wait()
        task_queue.stop()
        return

    # Start full pipeline
    logger.info("Starting StreamClipper with %d streamers...", len(streamers))
    manager.start(streamers, poll_interval=args.poll_interval)

    try:
        while not _shutdown_event.is_set():
            _shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        manager.stop()
        db.close()
        logger.info("StreamClipper stopped. Goodbye!")


if __name__ == "__main__":
    main()
