"""Upload history routes."""

from fastapi import APIRouter
from server.deps import get_db

router = APIRouter()


@router.get("/uploads")
async def list_uploads(limit: int = 50):
    db = get_db()
    return {"uploads": db.get_uploads(limit=limit)}
