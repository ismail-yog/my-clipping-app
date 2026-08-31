"""
StreamClipper — Dream Team API Routes
Endpoints to interact with the Dream Team AI agents.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("streamclipper.server.routes.dreamteam")

router = APIRouter()

# ── Lazy singleton Director ─────────────────────────────────────────────
_director = None

def _get_director():
    """Lazy-init the Dream Team Director."""
    global _director
    if _director is None:
        try:
            from dream_team.director import Director
            _director = Director()
            _director.initialise()
            logger.info("Dream Team Director initialised for API")
        except Exception as exc:
            logger.error("Failed to init Dream Team: %s", exc)
            raise HTTPException(status_code=503, detail=f"Dream Team unavailable: {exc}")
    return _director


# ── Pydantic Models ─────────────────────────────────────────────────────

class AnalyzeClipRequest(BaseModel):
    transcript: str = "This was absolutely insane! No way that just happened!"
    emotion: str = "surprise"
    clip_path: str = ""
    chat_intensity: float = 0.5

class SEORequest(BaseModel):
    transcript: str = "Oh my god he just clutched it! The whole chat went crazy!"
    emotion: str = "surprise"
    streamer_name: str = "TestStreamer"

class ModerationRequest(BaseModel):
    transcript: str = "This clip is so cool and exciting!"
    title: str = "Unbelievable Play!"
    description: str = "Watch this insane moment"
    tags: list = ["gaming", "viral"]
    emotion: str = "surprise"

class DiagnoseRequest(BaseModel):
    error_msg: str
    context: str = ""

class PipelineRequest(BaseModel):
    clip_id: str = "manual_test_001"
    clip_path: str = ""
    transcript: str = "Oh my god no way! He just hit the craziest shot!"
    emotion: str = "surprise"
    streamer_name: str = "TestStreamer"
    chat_intensity: float = 0.7
    title: str = "Crazy Moment!"
    description: str = "Watch this clip"
    tags: list = ["gaming", "clips"]


# ═══════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/status")
async def dream_team_status():
    """Get Dream Team status — which agents are active, cost, memory stats."""
    try:
        director = _get_director()
        return {
            "enabled": True,
            "ready": director.is_ready,
            "active_agents": director.active_agents,
            "agent_count": len(director.active_agents),
            "cost": director.get_cost_summary(),
            "memory": director.get_memory_stats(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


@router.get("/agents")
async def list_agents():
    """List all agents with their tools and descriptions."""
    director = _get_director()
    agents = []
    for name in director.active_agents:
        agent = director.get_agent(name)
        agents.append({
            "name": agent.name,
            "description": agent.description,
            "tools": list(agent._tools.keys()),
            "cost": f"${agent._agent_cost:.4f}",
        })
    return {"agents": agents, "count": len(agents)}


@router.get("/agents/{name}")
async def get_agent_detail(name: str):
    """Get details for a specific agent."""
    director = _get_director()
    agent = director.get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return {
        "name": agent.name,
        "description": agent.description,
        "tools": list(agent._tools.keys()),
        "cost": f"${agent._agent_cost:.4f}",
        "config": agent.agent_config,
        "repr": repr(agent),
    }


# ── Atlas: Viral Analysis ───────────────────────────────────────────────

@router.post("/atlas/analyze")
async def atlas_analyze(req: AnalyzeClipRequest):
    """Ask Atlas to analyze a clip's viral potential (uses LLM if available)."""
    director = _get_director()
    atlas = director.get_agent("atlas")
    if not atlas:
        raise HTTPException(status_code=503, detail="Atlas agent not loaded")
    result = atlas.analyze_clip(
        clip_path=req.clip_path,
        transcript=req.transcript,
        emotion=req.emotion,
        chat_intensity=req.chat_intensity,
    )
    return {"agent": "atlas", "result": result}


@router.post("/atlas/score")
async def atlas_score(req: AnalyzeClipRequest):
    """Quick viral score (heuristic, no LLM needed)."""
    director = _get_director()
    atlas = director.get_agent("atlas")
    if not atlas:
        raise HTTPException(status_code=503, detail="Atlas agent not loaded")
    score = atlas.score_virality(
        transcript=req.transcript,
        emotion=req.emotion,
        chat_intensity=req.chat_intensity,
    )
    return {"agent": "atlas", "viral_score": round(score, 3), "recommended": score >= 0.65}


@router.get("/atlas/trending")
async def atlas_trending(limit: int = 10):
    """Get trending viral patterns from Atlas."""
    director = _get_director()
    atlas = director.get_agent("atlas")
    if not atlas:
        raise HTTPException(status_code=503, detail="Atlas agent not loaded")
    return {"agent": "atlas", "patterns": atlas.get_trending_patterns(limit=limit)}


# ── Scribe: SEO Generation ──────────────────────────────────────────────

@router.post("/scribe/title")
async def scribe_title(req: SEORequest):
    """Generate a clickbait title for a clip."""
    director = _get_director()
    scribe = director.get_agent("scribe")
    if not scribe:
        raise HTTPException(status_code=503, detail="Scribe agent not loaded")
    title = scribe.generate_title(
        transcript=req.transcript,
        emotion=req.emotion,
        streamer_name=req.streamer_name,
    )
    return {"agent": "scribe", "title": title}


@router.post("/scribe/tags")
async def scribe_tags(req: SEORequest):
    """Generate SEO tags for a clip."""
    director = _get_director()
    scribe = director.get_agent("scribe")
    if not scribe:
        raise HTTPException(status_code=503, detail="Scribe agent not loaded")
    tags = scribe.generate_tags(
        transcript=req.transcript,
        emotion=req.emotion,
        streamer_name=req.streamer_name,
    )
    return {"agent": "scribe", "tags": tags}


@router.post("/scribe/full-seo")
async def scribe_full_seo(req: SEORequest):
    """Generate complete SEO package (title + description + tags)."""
    director = _get_director()
    scribe = director.get_agent("scribe")
    if not scribe:
        raise HTTPException(status_code=503, detail="Scribe agent not loaded")
    result = scribe.enhance_seo({
        "transcript": req.transcript,
        "emotion": req.emotion,
        "streamer_name": req.streamer_name,
    })
    return {"agent": "scribe", "result": result}


# ── Sentinel: Content Moderation ────────────────────────────────────────

@router.post("/sentinel/review")
async def sentinel_review(req: ModerationRequest):
    """Review clip content for safety and quality."""
    director = _get_director()
    sentinel = director.get_agent("sentinel")
    if not sentinel:
        raise HTTPException(status_code=503, detail="Sentinel agent not loaded")
    result = sentinel.review_clip({
        "transcript": req.transcript,
        "title": req.title,
        "description": req.description,
        "tags": req.tags,
        "emotion": req.emotion,
    })
    return {"agent": "sentinel", "result": result}


@router.post("/sentinel/profanity-check")
async def sentinel_profanity(text: str = "What the fuck was that play?!"):
    """Check text for profanity."""
    director = _get_director()
    sentinel = director.get_agent("sentinel")
    if not sentinel:
        raise HTTPException(status_code=503, detail="Sentinel agent not loaded")
    return {"agent": "sentinel", "result": sentinel.check_profanity(text)}


@router.post("/sentinel/moderate")
async def sentinel_moderate(req: ModerationRequest):
    """Full auto-moderation pipeline (approve/flag/reject)."""
    director = _get_director()
    sentinel = director.get_agent("sentinel")
    if not sentinel:
        raise HTTPException(status_code=503, detail="Sentinel agent not loaded")
    result = sentinel.auto_moderate({
        "transcript": req.transcript,
        "title": req.title,
        "description": req.description,
        "tags": req.tags,
        "emotion": req.emotion,
    })
    return {"agent": "sentinel", "result": result}


# ── Pixel: Visual Enhancement ───────────────────────────────────────────

@router.post("/pixel/thumbnail-text")
async def pixel_thumbnail_text(title: str = "Epic Clutch Moment", emotion: str = "surprise"):
    """Generate punchy thumbnail text."""
    director = _get_director()
    pixel = director.get_agent("pixel")
    if not pixel:
        raise HTTPException(status_code=503, detail="Pixel agent not loaded")
    text = pixel.suggest_thumbnail_text(title=title, emotion=emotion)
    return {"agent": "pixel", "thumbnail_text": text}


@router.get("/pixel/colors/{emotion}")
async def pixel_colors(emotion: str):
    """Get color scheme for an emotion."""
    director = _get_director()
    pixel = director.get_agent("pixel")
    if not pixel:
        raise HTTPException(status_code=503, detail="Pixel agent not loaded")
    return {"agent": "pixel", "emotion": emotion, "colors": pixel.suggest_colors(emotion)}


# ── Pulse: Performance Analytics ────────────────────────────────────────

@router.get("/pulse/trends")
async def pulse_trends(days: int = 7):
    """Analyze performance trends."""
    director = _get_director()
    pulse = director.get_agent("pulse")
    if not pulse:
        raise HTTPException(status_code=503, detail="Pulse agent not loaded")
    return {"agent": "pulse", "result": pulse.analyze_trends(days=days)}


@router.get("/pulse/best-time")
async def pulse_best_time():
    """Get best upload time recommendation."""
    director = _get_director()
    pulse = director.get_agent("pulse")
    if not pulse:
        raise HTTPException(status_code=503, detail="Pulse agent not loaded")
    return {"agent": "pulse", "best_upload_time": pulse.get_best_upload_time()}


@router.get("/pulse/report")
async def pulse_report(days: int = 7):
    """Get full performance report."""
    director = _get_director()
    pulse = director.get_agent("pulse")
    if not pulse:
        raise HTTPException(status_code=503, detail="Pulse agent not loaded")
    return {"agent": "pulse", "report": pulse.generate_report(days=days)}


# ── Debugger: System Health ─────────────────────────────────────────────

@router.get("/debugger/health")
async def debugger_health():
    """Run system health check."""
    director = _get_director()
    debugger = director.get_agent("debugger")
    if not debugger:
        raise HTTPException(status_code=503, detail="Debugger agent not loaded")
    return {"agent": "debugger", "result": debugger.check_system_health()}


@router.get("/debugger/logs")
async def debugger_logs():
    """Analyze Dream Team log files for errors."""
    director = _get_director()
    debugger = director.get_agent("debugger")
    if not debugger:
        raise HTTPException(status_code=503, detail="Debugger agent not loaded")
    return {"agent": "debugger", "result": debugger.analyze_logs()}


@router.post("/debugger/diagnose")
async def debugger_diagnose(req: DiagnoseRequest):
    """Diagnose an error message."""
    director = _get_director()
    debugger = director.get_agent("debugger")
    if not debugger:
        raise HTTPException(status_code=503, detail="Debugger agent not loaded")
    return {"agent": "debugger", "result": debugger.diagnose_error(req.error_msg, req.context)}


@router.post("/debugger/auto-fix")
async def debugger_auto_fix(issue: str = "temp_files"):
    """Attempt auto-fix for a known issue (temp_files, ollama_restart, missing_dirs)."""
    director = _get_director()
    debugger = director.get_agent("debugger")
    if not debugger:
        raise HTTPException(status_code=503, detail="Debugger agent not loaded")
    return {"agent": "debugger", "result": debugger.auto_fix(issue)}


# ── Full Pipeline ───────────────────────────────────────────────────────

@router.post("/pipeline")
async def run_full_pipeline(req: PipelineRequest):
    """Run a clip through the full Dream Team pipeline (all agents)."""
    director = _get_director()
    result = director.process_clip(req.model_dump())
    # Clean up non-serializable keys
    safe_result = {}
    for k, v in result.items():
        try:
            import json
            json.dumps(v)
            safe_result[k] = v
        except (TypeError, ValueError):
            safe_result[k] = str(v)
    return {"pipeline": "complete", "result": safe_result}


# ── Memory ──────────────────────────────────────────────────────────────

@router.get("/memory")
async def get_memory_stats():
    """Get shared memory usage stats."""
    director = _get_director()
    return {"memory": director.get_memory_stats()}


@router.get("/memory/search/{category}")
async def search_memory(category: str, limit: int = 20):
    """Search shared memory by category (clips, patterns, user_feedback, errors, performance)."""
    director = _get_director()
    results = director.memory.search(category=category, limit=limit)
    return {"category": category, "count": len(results), "entries": results}


# ── Cost ────────────────────────────────────────────────────────────────

@router.get("/cost")
async def get_cost():
    """Get API cost summary across all agents."""
    director = _get_director()
    return director.get_cost_summary()
