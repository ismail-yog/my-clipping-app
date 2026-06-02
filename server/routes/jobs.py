"""Job queue routes."""

from fastapi import APIRouter
from typing import Optional
from server.deps import get_db

router = APIRouter()


@router.get("/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 50):
    db = get_db()
    return {"jobs": db.get_jobs(status=status, limit=limit)}
