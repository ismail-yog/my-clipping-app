"""Status & scores routes."""

import time
from fastapi import APIRouter
from server.deps import get_db, get_pipeline_manager, get_task_queue

router = APIRouter()


@router.get("/status")
async def get_status():
    db = get_db()
    pm = get_pipeline_manager()
    tq = get_task_queue()

    data = {
        "timestamp": time.time(),
        "streamers": [],
        "active_pipelines": 0,
        "pipeline_active": pm.is_active if pm else False,
        "stats": db.get_stats(),
        "queue": tq.get_queue_stats() if tq else {},
    }

    if pm and pm.monitor:
        for key, st in pm.monitor.statuses.items():
            data["streamers"].append({
                "name": st.streamer.name,
                "platform": st.streamer.platform,
                "channel": st.streamer.channel,
                "is_live": st.is_live,
                "title": st.title,
                "game": st.game,
                "viewer_count": st.viewer_count,
                "last_checked": st.last_checked,
            })
        data["active_pipelines"] = len(pm.active_pipelines)

    return data


@router.get("/scores")
async def get_scores():
    pm = get_pipeline_manager()
    scores = []
    if pm:
        for key, pipeline in pm.active_pipelines.items():
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
    return {"scores": scores}


@router.post("/pipeline/start")
async def start_pipeline():
    import config
    pm = get_pipeline_manager()
    if not pm:
        return {"error": "Pipeline manager not initialized"}
    
    streamers = config.get_streamers()
    if not streamers:
        return {"error": "No streamers configured"}
        
    pm.start(streamers)
    return {"status": "started", "streamers_count": len(streamers)}


@router.post("/pipeline/stop")
async def stop_pipeline():
    pm = get_pipeline_manager()
    if not pm:
        return {"error": "Pipeline manager not initialized"}
        
    pm.stop()
    return {"status": "stopped"}

@router.post("/youtube/auth")
async def youtube_auth():
    import subprocess
    import os
    
    script_path = os.path.join(os.getcwd(), "auth_youtube.py")
    if not os.path.exists(script_path):
        return {"error": "auth_youtube.py not found"}
        
    try:
        # Run the script in the background. It will open the browser.
        # We don't block waiting for it because the user might take a while.
        subprocess.Popen(["python", script_path])
        return {"status": "auth_initiated", "message": "Browser opened for YouTube login"}
    except Exception as e:
        return {"error": f"Failed to start auth script: {e}"}
